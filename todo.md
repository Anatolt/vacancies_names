- сделать чтобы в истории хранилась не только ссылка но и вообще всё что напарсили

- натравить эту шутку, на вакансии на которые уже откликнулись в линкедине (вот ссылка https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED)
    - чтоб выкачивала и заполняла гугл таблицу / csv (что проще)
    - чтоб считала количество
    - чтоб проверяла соответствуют ли резюмешке и требованиям (клиент хочет не бекенд, а андроид) через llm

- ВАЖНО: discuss with LLM: make it usable from google spreadsheets / chrome extention
- добавить куки от гугла и авторизацию через гугл
- добавить мультипоточность через разные аккаунты и прокси
- ВАЖНО: добавить проверку не проверяли ли мы эти вакансии уже (я забываю сохранять файл links.txt) сохранять всё с чем работал скрипт в лог и проходиться по нему?
- переделать спонтанное закрытие браузера 
- добавить возможность парсить ваканси не только с линкедина
- ссылки линкедина типа feed обрабатывать по другому
- глобальный лог обработанных ссылок и результатов
- проверка на дубликаты
- Error with networkable

- [DONE] make screenshot of every vacancy scrypt visit (to use it in case when parse and llm html understandings failed. try to recognize screenshot with llm) - Реализовано в режиме --debug, сохраняет скриншоты в папку debug/screenshots/
- [DONE] save all text of the page to try to understand it with llm if it cant be parsed - Реализовано в режиме --debug, сохраняет HTML в папку debug/html/
- [DONE] fix cookies usage - scrypt save but do not use cookies for some reason - Исправлено: добавлена валидация cookies в linkedin_auth.json и улучшена работа с сохраненным состоянием
- [DONE] проверить как работает закрытие браузера посреди процесса - проверил, херово. надо переделывать
- [DONE] проверить как подхватываются куки - проверил. не работает
- [DONE] не работает авторизация по кукис. исправить
- [DONE] переделать вывод, чтоб легче вставлялось в гугл док
- discuss with LLM: refactore from on file to separate?
- [DONE] check start and finish time of each vacancy and whole process
- [DONE] вести лог скорости работы скрипта при каждом запуске 


- [DONE] добавить в env example TELEGRAM_USERID TELEGRAM_TOKEN, (2025/07/16)
- [DONE] добавить в readme команду 'cp env.example .env' (2025/07/16 )

todo 2025-07-08
- [DONE] разделить файл one на части
    Реализовано:
    main.py — точка входа с аргументами командной строки
    process_links.py — основная логика обработки ссылок
    linkedin_auth.py — модуль авторизации LinkedIn
    utils.py — общие функции (браузер, телеграм, debug)
    parsers/ — пакет парсеров:
      ├── linkedin.py — парсер LinkedIn
      ├── generic.py — парсер для других сайтов
      └── __init__.py
- [DONE] (отправлять лог в телегу для сохранности)
