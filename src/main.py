from evdev import InputEvent
from asyncio import create_task, CancelledError, Task
from contextlib import asynccontextmanager
from evdev import list_devices, ecodes, InputDevice
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from json import dump, load
from os.path import abspath, dirname, exists, join
from sys import stderr
from time import time
from typing import cast, AsyncGenerator
from uvicorn import run
from web_socket_manager import JsonElement, WebSocketManager


base_dir: str = dirname(abspath(__file__))
config_path: str = join(base_dir, "config.json")
split_data_path: str = join(base_dir, "split_data.json")
overlay_html_path: str = join(base_dir, "overlay.html")
icon_path: str = join(base_dir, "logo.ico")

with open(config_path, "r") as f:
    config = load(f)


api_port: int = config["API_PORT"]
split_key: str = config["SPLIT_KEY"]
pause_key: str = config["PAUSE_KEY"]


split_key_code: int = ecodes.ecodes[split_key]
pause_key_code: int = ecodes.ecodes[pause_key]


splits: list[float]
current_split: int
if exists(split_data_path):
    with open(split_data_path, "r") as f:
        split_data = load(f)

    splits = split_data["splits"]
    current_split = split_data["current_split"]
else:
    splits = [0.0] * 91
    current_split = 0

is_current_split_paused: bool = True
time_unpaused: float = 0.0


ws_manager = WebSocketManager()


def should_read_device(device: InputDevice[str]) -> bool:
    for event, codes in device.capabilities().items():
        if event != ecodes.EV_KEY:
            continue

        if split_key_code in codes or pause_key_code in codes:
            return True

    return False


def get_devices() -> list[InputDevice[str]]:
    all_devices: list[InputDevice[str]] = [InputDevice(path) for path in list_devices()]
    return list(filter(should_read_device, all_devices))


def save_current_split() -> None:
    if current_split >= 0 and current_split < len(splits):
        splits[current_split] += time() - time_unpaused

    with open(split_data_path, "w") as f:
        dump({"splits": splits, "current_split": current_split}, f)


async def broadcast_state() -> None:
    await ws_manager.broadcast(
        {
            "splits": cast(JsonElement, splits),
            "current_split": current_split,
            "is_current_split_paused": is_current_split_paused,
        }
    )


async def read_device_events(device: InputDevice[str]) -> None:
    global current_split, is_current_split_paused, time_unpaused
    async for event in device.async_read_loop():
        input_event: InputEvent = event

        if input_event.type != ecodes.EV_KEY:
            continue

        if input_event.value != 1:
            continue

        if input_event.code == split_key_code:
            if is_current_split_paused:
                is_current_split_paused = False
            else:
                save_current_split()
                current_split = min(current_split + 1, len(splits))

            time_unpaused = time()
            await broadcast_state()
            continue

        if input_event.code == pause_key_code:
            if is_current_split_paused:
                continue

            save_current_split()
            is_current_split_paused = True
            await broadcast_state()
            continue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    devices: list[InputDevice[str]] = get_devices()
    tasks: list[Task[None]] = []
    for device in devices:
        tasks.append(create_task(read_device_events(device)))

    try:
        yield
    except CancelledError:
        pass
    except Exception as e:
        print(e, file=stderr)
    finally:
        print()
        print("Shutting down")
        for task in tasks:
            task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(icon_path)


@app.websocket("/ws")
async def overlay_websocket(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    await broadcast_state()
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, CancelledError):
        pass
    finally:
        ws_manager.disconnect(websocket)


@app.get("/", response_class=HTMLResponse)
async def overlay() -> HTMLResponse:
    with open(overlay_html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


if __name__ == "__main__":
    run("main:app", host="127.0.0.1", port=api_port)
