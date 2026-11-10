# Ігри на Feodal / Arch Linux

Почни з діагностики й інструкції:

```sh
feodal-gaming
feodal-gaming install
```

Перша команда лише читає PCI sysfs, наявність Steam та налаштування multilib.
Друга після перевірок і окремого підтвердження запускає повне оновлення Arch і
встановлює `steam`, Mesa та 64-/32-бітний Intel Vulkan. Вона не змінює
`pacman.conf`, не встановлює AUR-пакети й не налаштовує NVIDIA. Відмовся від
підтвердження, якщо спершу хочеш переглянути план pacman.

## Наявні налаштування Feodal

Відкрий **Налаштування** на панелі, натисни **Super + I**, або запусти
`feodal-panel --settings`. Вікно створюється лише на запит; резидентного сервісу
немає. Там залишаються діагностика системи, вибір GPU для Steam та інші
налаштування. `feodal-gaming` — окрема CLI-команда, не кнопка в панелі.

### Діагностика обладнання

`feodal-hardware` повертає JSON зі станом ядра, RAM, PCI/DRM GPU, прив’язаним
драйвером і наявністю Steam/PRIME. Опитування `nvidia-smi` має тайм-аут і може
вивести NVIDIA GPU зі сну; адміністраторські права не потрібні. Успішна відповідь
NVIDIA не доводить роботу Vulkan, PRIME чи конкретної гри, а наявність
`prime-run` сама по собі не підтверджує драйвер.

### Вибір GPU у панелі

- **Звичайний запуск:** запускає `steam` без примусового вибору GPU.
- **NVIDIA / PRIME:** запускає `prime-run steam`, лише коли Steam і PRIME
  наявні, а діагностика підтвердила NVIDIA. Якщо чогось бракує, панель пояснює
  проблему замість тихого переходу на інший GPU чи встановлення пакетів.

Перед перемиканням повністю закрий Steam. Режим впливає лише на кнопки Steam
панелі й центру керування; не переписує `.desktop` файли, не змінює запуск із
меню програм і не перемикає GPU сеансу глобально. Налаштування зберігається в
`$XDG_CONFIG_HOME/feodal/preferences.json` або
`~/.config/feodal/preferences.json`; у непостійному live-сеансі воно зникне після
перезапуску. Для окремої гри використовуй `prime-run %command%` лише після
перевірки драйвера.

## Увімкнути multilib

Якщо команда повідомляє, що multilib не підтверджено, вручну розкоментуй у
`/etc/pacman.conf` секцію:

```ini
[multilib]
Include = /etc/pacman.d/mirrorlist
```

Потім виконай повне оновлення системи (`sudo pacman -Syu`). Не роби часткове
оновлення лише баз пакетів. Після цього можна запустити `feodal-gaming install`.
Пакет `steam` з офіційного multilib Arch — рекомендований ArchWiki спосіб
встановлення Steam. Установлення Intel-пакетів дає робочий Vulkan і 32-бітну
графіку для вбудованого Intel GPU та Steam; helper навмисно не вгадує драйвер
для сторонньої відеокарти.

## NVIDIA MX330 (Pascal)

MX330 — гібридна Pascal-відеокарта. Актуальна таблиця NVIDIA в ArchWiki
спрямовує Pascal на legacy-пропрієтарний `nvidia-580xx-dkms` з AUR. `nvidia-open`
для Pascal не підходить. Для DKMS потрібні `dkms` і заголовки ядра, що реально
запускається (наприклад, `linux-headers` для звичайного `linux`, або відповідні
заголовки встановленого іншого ядра). Також NVIDIA-драйвер має збігатися за
версією між 64-бітними й 32-бітними бібліотеками.

Шлях 580xx та 32-бітні бібліотеки не входять до офіційного Arch репозиторію:
потрібні AUR-пакети `nvidia-580xx-utils`, `nvidia-580xx-dkms` і
`lib32-nvidia-580xx-utils` з узгодженої версії. Переглянь PKGBUILD та джерела
кожного пакета, перш ніж вручну збирати AUR звичайним користувачем; не запускай
`makepkg` від root і не змішуй ці пакети з `nvidia-utils`/
`lib32-nvidia-utils` поточної гілки. Помічник не завантажує, не перевіряє й не
збирає AUR-код.

Для ноутбука залиш Intel графіку основним GPU. Не встановлюй `nvidia-prime`
без перевірки плану pacman: цей офіційний пакет залежить від загальної назви
`nvidia-utils`, а середовище з 580xx може натомість вибрати сучасний офіційний
`nvidia-utils` (наприклад, 615.78.08), несумісний із Pascal. Спершу встановлюй
узгоджені legacy NVIDIA пакети; після цього перевір pacman transaction і фактичні
версії. Наявність `nvidia-prime` сама собою не доводить, що встановлено сумісний
драйвер.

Для ручного запуску Steam-гри на NVIDIA, без залежності від пакета `nvidia-prime`,
використай параметр запуску гри:

```text
__NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only __GLX_VENDOR_LIBRARY_NAME=nvidia %command%
```

Це той самий набір змінних, який задає `prime-run`; він не встановлює драйвер і
не обходить потребу у відповідних 64-/32-бітних legacy бібліотеках. Перевір
спочатку на конкретній системі. Не додавай GPU-перемикачі глобально для всіх
програм.

MX330 та 8 GiB RAM — обмежене ігрове обладнання: результат залежить від гри,
роздільності, охолодження, пам'яті й драйвера. Сумісність Proton перевіряй для
кожної гри окремо; античіт і DRM можуть не працювати в Linux. Ця інструкція не
обіцяє FPS і не підтверджує фізичне обладнання чи конкретні ігри.

Dota 2 має нативну Linux-версію; для GTA V Legacy Story Mode потрібен Proton.
GTA Online має обмеження BattlEye під Linux, які оболонка Feodal не усуває.

## Сеанс

Перед запуском панелі та Openbox сеанс передає `DISPLAY`, `XAUTHORITY` і змінні
XDG у середовище активації D-Bus/systemd-user. Це допомагає активованим графічним
службам знайти поточний X11 дисплей; решта змінних процесу не передається.

## Джерела

- [ArchWiki: Steam](https://wiki.archlinux.org/title/Steam)
- [ArchWiki: NVIDIA](https://wiki.archlinux.org/title/NVIDIA)
- [ArchWiki: Intel graphics](https://wiki.archlinux.org/title/Intel_graphics)
- [ArchWiki: PRIME](https://wiki.archlinux.org/title/PRIME)
- [ArchWiki: Official repositories / multilib](https://wiki.archlinux.org/title/Official_repositories#multilib)
- [AUR: nvidia-580xx-dkms](https://aur.archlinux.org/packages/nvidia-580xx-dkms)
- [AUR: nvidia-580xx-utils](https://aur.archlinux.org/packages/nvidia-580xx-utils)
- [AUR: lib32-nvidia-580xx-utils](https://aur.archlinux.org/packages/lib32-nvidia-580xx-utils)
