# Студия ТадамШоу

Инструменты, чтобы делать мультфильмы кукольного театра для [ТадамШоу](https://tadamshow.com): кукольный
движок, команда `tadam` и (скоро) скил для Claude Code. У вас на диске лежит **папка мира**; Claude пишет
сценарий, делает кукол и декорации, сам смотрит кадры и показывает вам сцену в локальном плеере. Когда всё
готово, одна команда отправляет работу в ТадамШоу на одобрение.

> Состояние: начало. Работают `tadam doctor`, `new`, `hero make`, `set make`, `check` и движок. Впереди:
> локальный плеер и кадры (`play`, `frames`, `film`), отправка в ТадамШоу (`login`, `push`, ...), скил.

English: [README.md](README.md).

## Лицензия в одном абзаце

Исходный код доступен (source-available), но это **не «open source»**: программа выпущена по лицензии
[PolyForm Noncommercial 1.0.0](LICENSE). Бесплатно для личного использования, хобби,
учёбы и исследований. Чтобы делать с её помощью мультфильмы, ролики или продукты в коммерческих целях, нужна
коммерческая лицензия. **Делать рубрики и серии для ТадамШоу можно** (см. [NOTICE](NOTICE)). Содержимое
рубрик, имя и логотип «ТадамШоу» лицензией не покрыты. За коммерческой лицензией — откройте issue с заголовком
"Commercial licence".

## Установка за 5 минут

Нужно:

1. **Python 3.11+** — https://www.python.org/downloads/
2. **Godot 4.7** (обычная сборка, не .NET) — https://godotengine.org/download/
   В `PATH` (как `godot`, `godot4` или `godot_console`) или полный путь в переменной `TADAM_GODOT`.
3. **ffmpeg** вместе с `ffprobe` — https://ffmpeg.org/download.html
4. **Свой ключ OpenAI** в переменной окружения `OPENAI_API_KEY` — https://platform.openai.com/api-keys
   На нём рисуются ваши куклы и декорации; ничего платного от нас нет. Не кладите ключ в файлы репозитория;
   лучше всего — менеджер секретов.
5. **Ключ студии** со страницы студии ТадамШоу — позже, только для отправки работ (`tadam login`).

Потом:

```bash
git clone https://github.com/unbywyd/tadamshow-studio.git
cd tadamshow-studio
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS / Linux: source .venv/bin/activate
pip install -e .
tadam doctor
```

`tadam doctor` проверяет Python, Godot, ffmpeg, ключ OpenAI (только что он задан; значение не печатается) и
временную папку, и говорит, чего не хватает и где это взять. Код выхода 1 — не хватает обязательного.

## Команды

```bash
tadam new world my-world --title "Моя рубрика"   # папка мира (world.json с «библией»)
cd my-world
tadam new hero cow --name "Корова"                # heroes/cow/hero.json
tadam hero make cow "a calm brown cow in a raincoat"   # кукла: рисует ВАШИМ ключом, режет, проверяет
tadam new set barn                                # sets/barn/kit.json: опишите комнату и мебель
tadam set make barn                               # декорация: рисует ВАШИМ ключом, пишет set.json
tadam new episode 1 --cast cow=cow                # episodes/1/script.json (сценарий версии 2)
tadam check 1                                     # что не так, простыми словами; выход 1 при ошибках; --json
```

`hero make --mannequin` и `set make --placeholder` рисуют кодом бесплатные заглушки (деревянный манекен,
простая комната), чтобы расставить сцену до платной генерации. `tadam check --engine` дополнительно
проигрывает каждый план в движке без окна. Служебная папка `.tadam/` мира (сцены движка, кеш) не коммитится
и не отправляется.

## Помощь проекту и безопасность

[CONTRIBUTING.md](CONTRIBUTING.md) и [SECURITY.md](SECURITY.md).
