использовать существующий хром, а не качать отдельный хромиум:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    # Используем ваш установленный Chrome
    browser = p.chromium.launch(
        executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe",  # путь к вашему Chrome
        headless=False
    )
```
