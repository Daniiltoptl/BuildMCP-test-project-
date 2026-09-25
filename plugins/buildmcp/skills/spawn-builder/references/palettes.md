# Палитры и фактура

## Принципы

- **60-30-10:** основной материал (60%), второстепенный (30%), акцент (10%).
- **Кластеры, не шум:** `P.patches({...}, size=3..7)` вместо `P.mix`. Порядок ключей важен: соседние в
  списке блоки граничат пятнами, поэтому ставь их как градиент (светлый → средний → тёмный).
- **Градиенты:**
  - по высоте `P.gradient([...], axis="y", start=верх, end=низ)`: темнее и грязнее к низу;
  - по расстоянию от центра (`axis="radial"`);
  - по глубине слоя (террейн это уже делает).
- **Состаривание:** у основания стен больше мха и трещин (mossy/cracked), вверху чище.
- **Контраст значений:** соседние объекты различаются по светлоте (светлая стена, тёмная крыша, тёмное
  дерево рам). Проверяй на рендере в оттенках: если всё одного тона, добавь тёмные рамы или светлую
  отделку.
- **Насыщенность дозированно:** яркие блоки (шерсть, бетон, золото) только акцентами. Основа —
  природные камни, дерево, терракота.

## Проверенные смеси (1.21)

- Камень, светлый: `stone_bricks 6, cracked_stone_bricks 1, mossy_stone_bricks 1, tuff_bricks 0.8, andesite 0.6`.
- Камень, скальный: `stone 5, andesite 3, tuff 1.5, cobblestone 1, mossy_cobblestone 0.8`.
- Глубинный камень: `deepslate 4, cobbled_deepslate 2, tuff 2, andesite 1`.
- Штукатурка: `calcite 4, white_terracotta 1.5, smooth_quartz 1`.
- Брусчатка площади: `stone_bricks 5, polished_andesite 2, cracked_stone_bricks 1, mossy_stone_bricks 1, andesite 1`.
- Тропа: `dirt_path 6, coarse_dirt 2, gravel 1.2, packed_mud 1` (dirt_path на 1/16 ниже, тропа
  «вдавлена»).
- Трава: `moss_block 2, grass_block 10, podzol 0.8, coarse_dirt 0.6`.
- Листва фэнтези: `oak_leaves 5, azalea_leaves 2, flowering_azalea_leaves 1, dark_oak_leaves 1.2`.
- Крыша тёмная: `deepslate_tiles` (ступени и полублоки) + рёбра `dark_oak`.
- Тёмная тема, стены: `polished_blackstone_bricks 5, cracked_… 1.5, nether_bricks 2, deepslate_tiles 1`.
- Зимняя тема, скалы: `stone 4, andesite 2, calcite 1.5, diorite 1`, лёд `packed_ice 4, blue_ice 2, ice 1`.

## Инструменты

- `palette(action="gradient", a="deepslate", b="calcite", steps=7, sets="stone")`: плавный переход.
- `palette(action="similar", a="stone_bricks")`: похожие по цвету блоки для фактуры.
- `palette(action="nearest", color=[r,g,b])`: блок под цвет из референса.
- `colors.gradient_between(...)` и `colors.similar(...)` доступны и в скриптах.
- Темы: `T.grass`, `T.rock`, `T.wall`, `T.plaster`, `T.plaza`, `T.path`, `T.leaves`, `T.roof` и т.д.
  (`inspect(what="theme")`).

## Типичные ошибки

- Одна текстура на огромной площади: stone_bricks 20×10 без вариаций.
- Радуга: слишком много разных материалов, нет системы.
- Шум: случайная смесь несочетаемых блоков (гладкий кварц с булыжником).
- Одинаковая светлота всего: нет тёмных рам и светлой отделки.
