# Claude Design handoff — IVAN Index Terminal

Эта папка — **эталон макета** из Claude Design. Не удалять.

| Файл | Назначение |
|------|------------|
| `IVAN-Terminal-v5.dc.html` | Интерактивный прототип (разметка + логика) |
| `support.js` | Runtime Claude Design (нужен, чтобы открыть `.dc.html` в браузере) |
| `DESIGN.md` | Спека: токены, экраны, поведение |

## Как смотреть прототип

Откройте файл через локальный сервер (не `file://`), например:

```bash
# из корня репозитория
python3 -m http.server 8765 --directory ivan/design-handoff
```

Затем: http://127.0.0.1:8765/IVAN-Terminal-v5.dc.html

## Связь с продакшеном

Рабочий сайт собирается из `ivan/home.html`, `ivan/detail.html`, `ivan/js/*`, `ivan/css/terminal.css`.  
При расхождениях UI сверять сначала с этим handoff.

Zip-архив `ivan/Data-продукт*.zip` в git не храним (см. `.gitignore`) — хранится распакованная копия здесь.
