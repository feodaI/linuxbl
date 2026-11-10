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

Для ноутбука залиш Intel графіку основним GPU, а для окремої гри спробуй
`prime-run %command%` у Steam, якщо налаштовані сумісний драйвер і `prime-run`.
Спочатку перевір вивід `prime-run` та Vulkan; це не гарантує роботу конкретної
гри. Не додавай параметри примусового вибору GPU глобально.

MX330 та 8 GiB RAM — обмежене ігрове обладнання: результат залежить від гри,
роздільності, охолодження, пам'яті й драйвера. Сумісність Proton перевіряй для
кожної гри окремо; античіт і DRM можуть не працювати в Linux. Ця інструкція не
обіцяє FPS і не підтверджує фізичне обладнання чи конкретні ігри.

## Джерела

- [ArchWiki: Steam](https://wiki.archlinux.org/title/Steam)
- [ArchWiki: NVIDIA](https://wiki.archlinux.org/title/NVIDIA)
- [ArchWiki: Intel graphics](https://wiki.archlinux.org/title/Intel_graphics)
- [ArchWiki: PRIME](https://wiki.archlinux.org/title/PRIME)
- [ArchWiki: Official repositories / multilib](https://wiki.archlinux.org/title/Official_repositories#multilib)
- [AUR: nvidia-580xx-dkms](https://aur.archlinux.org/packages/nvidia-580xx-dkms)
- [AUR: nvidia-580xx-utils](https://aur.archlinux.org/packages/nvidia-580xx-utils)
- [AUR: lib32-nvidia-580xx-utils](https://aur.archlinux.org/packages/lib32-nvidia-580xx-utils)
