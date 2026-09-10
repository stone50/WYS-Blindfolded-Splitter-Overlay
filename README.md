# Usage

- To permit reading kernel inputs when not running as `root`, run `sudo usermod -aG input $USER`

- In the same directory as the executable, add a `config.json` file:
```
{
    "API_PORT": <port number>,
    "SPLIT_KEY": <key name>,
    "PAUSE_KEY": <key name>
}
```
For key names, see https://python-evdev.readthedocs.io/en/latest/ecodes.html

- In OBS, create a browser source with the URL set to `http://127.0.0.1:<port number>`, and the size set to 2400x425.

- Now when you run this project, OBS should display the overlay. It may be required to refresh or deactivate+reactivate the browser source depending on your setup.
