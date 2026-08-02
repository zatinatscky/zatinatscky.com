# Handoff: zatinatscky.com — сайт-визитка (редизайн)

## Overview
Одностраничный сайт-визитка консультанта Ивана Затинацкого с клиентской навигацией по четырём разделам (Главная, Обо мне, Статьи, Продукты) и переключателем языка RU/EN. Структура и навигация повторяют существующий сайт https://zatinatscky.com/; визуальный язык (цвет, типографика) взят из внутренней дизайн-системы «IVAN Terminal».

## About the Design Files
Файлы в этом бандле — **дизайн-референс, сделанный в HTML**: прототип, показывающий задуманный вид и поведение, а не продакшн-код для копирования. Задача — **воспроизвести эти макеты в целевой кодовой базе** (Next.js/Astro/React/Vue/статический генератор) её же паттернами и библиотеками. Если кодовой базы ещё нет — для сайта-визитки достаточно статического генератора (Astro или Next.js со статическим экспортом) либо чистого HTML/CSS; SPA-роутер не обязателен, разделы можно сделать отдельными URL (/, /about, /articles, /products) с i18n-префиксом (/en/...).

`Zatinatscky Site.dc.html` — прототип. Он использует внутренний рантайм (`support.js`, шаблон + класс логики). Переносить нужно разметку, стили и поведение, а не рантайм.

## Fidelity
**High-fidelity.** Цвета, типографика, отступы и состояния — финальные. Копия текста в разделах «Обо мне» и «Продукты» — плейсхолдеры, помеченные как заготовки: их заменяет владелец сайта.

## Screens / Views

Общая обёртка: `min-height:100vh`, фон `#EBEBEB`, цвет текста `#013547`, шрифт по умолчанию Archivo. Контент-контейнер: `max-width:1080px; margin:0 auto; padding:0 32px`.

### Header (глобальный)
- Sticky, `top:0`, `z-index:5`, фон `rgba(235,235,235,.92)` + `backdrop-filter: blur(10px)`, нижняя граница `1px solid rgba(1,53,71,.13)`.
- Внутри: `max-width:1080px; padding:18px 32px; display:flex; align-items:center; gap:28px`.
- **Логотип** (клик → Главная, `cursor:pointer`, `margin-right:auto`): две строки, `gap:3px`.
  - «Иван Затинацкий» — Newsreader, italic, 21px/1.
  - «КОНСАЛТИНГ» — IBM Plex Mono 500, 9px/1, `letter-spacing:.2em`, uppercase, `#8b9aa0`.
- **Nav**: `display:flex; gap:22px`. Пункты: Обо мне / Статьи / Продукты. IBM Plex Mono 500 12px, `letter-spacing:.1em`, uppercase, `padding-bottom:3px`.
  - Неактивный: цвет `#6C6F6E`, `border-bottom:1px solid transparent`.
  - Активный: цвет `#013547`, `border-bottom:1px solid #DDBA9B`.
- **Переключатель языка**: `display:flex; gap:6px; padding-left:22px; border-left:1px solid rgba(1,53,71,.13)`. Кнопки RU / EN, IBM Plex Mono 500 11px, `letter-spacing:.1em`, `padding:5px 9px`.
  - Активная: фон `#013547`, текст `#EBEBEB`, рамка `1px solid #013547`.
  - Неактивная: фон прозрачный, текст `#8b9aa0`, рамка прозрачная.

### 1. Главная (index)
- **Purpose**: позиционирование в одну фразу + три входа в разделы.
- **Layout**: `padding:112px 0 96px; max-width:820px`. Анимация появления `zrise .5s cubic-bezier(.16,1,.3,1) both`.
- **Компоненты**:
  - Кикер «ГЛАВНАЯ» / «HOME»: IBM Plex Mono 500 10px, `letter-spacing:.22em`, uppercase, `#8b9aa0`, `margin-bottom:28px`.
  - H1: Newsreader 400, `clamp(40px,6vw,72px)`, `line-height:1.06`, `letter-spacing:-.02em`, `text-wrap:pretty`. Вторая часть фразы курсивом (`font-style:italic`).
    - RU: «Стратегия и ясность *без лишнего шума*». EN: «Strategy and clarity *without the noise*».
  - Лид-абзац: 19px/1.62, `#6C6F6E`, `max-width:600px`, `margin-top:32px`.
  - Кнопки (`display:flex; flex-wrap:wrap; gap:12px; margin-top:44px`), все — IBM Plex Mono 500 12px, `letter-spacing:.12em`, uppercase, `padding:13px 22px`, без радиуса:
    - Primary «Обо мне →»: фон `#013547`, текст `#EBEBEB`; hover — `#022733`.
    - Secondary «Статьи», «Продукты»: `border:1px solid rgba(1,53,71,.3)`; hover — фон и рамка `#DDBA9B`.
  - Подпись внизу: `margin-top:80px; border-top:1px solid rgba(1,53,71,.13); padding-top:22px; display:flex; gap:14px; align-items:center`. Каретка «▍» IBM Plex Mono 500 20px, цвет `#DDBA9B`, анимация `zcaret 1.4s steps(1) infinite` (opacity 1 → .12 → 1). Текст «структура · данные · здравый смысл» / «structure · data · common sense», IBM Plex Mono 400 12px, `letter-spacing:.1em`, `#8b9aa0`.

### 2. Обо мне (about)
- **Purpose**: биография, ценности, контакт и форматы работы.
- **Layout**: `padding:84px 0 96px`. Кикер (как на главной) → H1 Newsreader 400 `clamp(36px,5vw,58px)`, `line-height:1.08`, `margin-bottom:64px`.
- Далее два блока-строки, каждый: `display:grid; grid-template-columns:200px 1fr; gap:48px; border-top:1px solid rgba(1,53,71,.13); padding-top:28px` (второй ещё `margin-top:56px`).
  - Левая колонка — подзаголовок: IBM Plex Mono 500 11px, `letter-spacing:.16em`, uppercase, `#013547`, `margin-top:4px`. Значения: «Профиль» / «Profile», «Контакт и формат» / «Contact & formats».
  - Правая колонка: `max-width:620px; display:flex; flex-direction:column; gap:20px` (во втором блоке `gap:24px`). Абзацы 17px/1.68; первый — `#013547`, второй — `#6C6F6E`.
  - **Карточка контакта** (второй блок): фон `#F7F6F4`, `border:1px solid rgba(1,53,71,.13)`, `padding:24px`, `gap:10px`. Лейбл «EMAIL» — IBM Plex Mono 500 10px, `letter-spacing:.18em`, uppercase, `#8b9aa0`. Адрес — IBM Plex Mono 500 20px, `#013547`, `border-bottom:1px solid #DDBA9B`, `align-self:flex-start`, ссылка `mailto:`. Подпись 14px/1.6 `#6C6F6E`.

### 3. Статьи (articles)
- **Purpose**: список публикаций.
- **Layout**: кикер → H1 (как в «Обо мне», без нижнего margin) → лид-абзац 17px/1.65 `#6C6F6E`, `max-width:560px`, `margin-top:22px`.
- **Сетка карточек**: `display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:1px; background:rgba(1,53,71,.13); border:1px solid rgba(1,53,71,.13); margin-top:56px` — «хайрлайн-сетка» (фон контейнера просвечивает как разделители).
- **Карточка** (`<a>`): фон `#F7F6F4`, `padding:32px 28px 36px`, `display:flex; flex-direction:column; gap:14px; min-height:250px`. Hover: фон `#DDBA9B`.
  - Мета «2026 · заметка»: IBM Plex Mono 500 10px, `letter-spacing:.16em`, uppercase, `#8b9aa0`.
  - Заголовок: Newsreader 400 27px, `line-height:1.18`.
  - Анонс: 15px/1.6, `#6C6F6E`.
  - CTA «Читать →»: `margin-top:auto`, IBM Plex Mono 500 11px, `letter-spacing:.12em`, uppercase, `#013547`.
- **Пустая карточка-заглушка** (не ссылка): фон `#EBEBEB`, весь текст `#8b9aa0`, без CTA. Держит ритм сетки — при реальном контенте убрать.

### 4. Продукты (products)
- **Purpose**: перечень услуг с призывом связаться.
- **Layout**: кикер → H1 «Продукты *и услуги*» (вторая часть курсивом) → лид 17px/1.65 `#6C6F6E`, `max-width:560px`.
- **Список строк**: контейнер `display:flex; flex-direction:column; margin-top:56px; border-top:1px solid rgba(1,53,71,.13)`.
- **Строка услуги**: `display:grid; grid-template-columns:210px 1fr auto; gap:32px; align-items:start; padding:32px 4px; border-bottom:1px solid rgba(1,53,71,.13)`. Hover: фон `#F7F6F4`.
  - Колонка 1 — формат: IBM Plex Mono 500 10px, `letter-spacing:.16em`, uppercase, `#8b9aa0`, `padding-top:8px`. Значения: «Формат · 2–4 недели», «Формат · сессии», «Формат · ongoing».
  - Колонка 2 — `max-width:560px; gap:10px`: заголовок Newsreader 400 29px/1.15; описание 16px/1.6 `#6C6F6E`.
  - Колонка 3 — кнопка «Запросить →»: IBM Plex Mono 500 11px, `letter-spacing:.12em`, uppercase, `padding:11px 18px`, `border:1px solid rgba(1,53,71,.3)`, `white-space:nowrap`; hover — фон и рамка `#DDBA9B`. Ведёт в раздел «Обо мне» (там контакты); в проде — `mailto:` или форма.
  - Три услуги: Диагностика процесса / Стратегическая сессия / Сопровождение руководителя.

### Footer (глобальный)
`border-top:1px solid rgba(1,53,71,.13); margin-top:auto`; внутри `max-width:1080px; padding:26px 32px; display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:16px`. Текст IBM Plex Mono 400 11px, `letter-spacing:.1em`, uppercase, `#8b9aa0`. Слева «© консалтинг» / «© consulting», справа ссылка «контакты в разделе «Обо мне»» — цвет `#013547`, `border-bottom:1px solid #DDBA9B`.

## Interactions & Behavior
- **Навигация**: клик по пункту меню / кнопке / логотипу меняет активный раздел, `preventDefault()`, `window.scrollTo(0,0)`. В проде — реальные роуты и скролл в начало при переходе.
- **Язык**: RU/EN переключает весь контент страницы синхронно; выбранный раздел сохраняется. В проде — i18n-словари и языковой префикс URL; желательно запоминать выбор (localStorage / cookie) и учитывать `Accept-Language`.
- **Появление раздела**: `@keyframes zrise` — `opacity:0; translateY(14px)` → `opacity:1; none`, `.5s cubic-bezier(.16,1,.3,1) both`. Уважать `prefers-reduced-motion`.
- **Каретка**: `@keyframes zcaret` — `0%,100%{opacity:1} 50%{opacity:.12}`, `1.4s steps(1) infinite`.
- **Hover-состояния**: описаны выше по компонентам; переходов (transition) в прототипе нет — при желании добавить `transition: background .15s ease`.
- **Selection**: `::selection { background: rgba(221,186,155,.55) }`.
- **Ссылки**: базовый цвет `a` и `a:hover` — `#013547`, `text-decoration:none`.
- **Responsive**: прототип рассчитан на десктоп. Для мобильных: сетки `200px 1fr` и `210px 1fr auto` схлопнуть в одну колонку; nav — в бургер или горизонтальный скролл; `padding` контейнера 32px → 20px. Сетка карточек статей адаптивна из коробки (`auto-fit minmax(280px,1fr)`).
- **Loading / error / формы**: в дизайне отсутствуют — контакт через `mailto:`.

## State Management
Два значения:
- `page: 'index' | 'about' | 'articles' | 'products'` — активный раздел (в проде: URL-роут).
- `lang: 'ru' | 'en'` — язык (в проде: локаль из URL-префикса).
Внешних данных нет; статьи и услуги в прототипе захардкожены — в проде это могут быть markdown/CMS-коллекции.

## Design Tokens

**Цвета**
| Токен | Значение | Применение |
|---|---|---|
| bg | `#EBEBEB` | фон страницы, заглушка-карточка |
| surface | `#F7F6F4` | карточки, hover строк услуг |
| ink | `#013547` | основной текст, primary-кнопка, активные состояния |
| ink-hover | `#022733` | hover primary-кнопки |
| muted | `#6C6F6E` | вторичный текст, неактивные пункты меню |
| faint | `#8b9aa0` | мета-подписи, кикеры, футер |
| accent | `#DDBA9B` | подчёркивания, hover-заливки, каретка |
| accent-selection | `rgba(221,186,155,.55)` | ::selection |
| hairline | `rgba(1,53,71,.13)` | все разделители и рамки |
| hairline-strong | `rgba(1,53,71,.3)` | рамки secondary-кнопок |
| on-ink | `#EBEBEB` | текст на тёмном |

**Типографика** — Google Fonts: Newsreader (400/500 + italic, opsz 6..72), Archivo (400/500/600), IBM Plex Mono (400/500/600).
| Роль | Стиль |
|---|---|
| H1 главная | Newsreader 400, clamp(40px,6vw,72px)/1.06, ls -.02em |
| H1 раздела | Newsreader 400, clamp(36px,5vw,58px)/1.08, ls -.02em |
| H3 услуга | Newsreader 400, 29px/1.15 |
| H3 карточка | Newsreader 400, 27px/1.18 |
| Лид | Archivo 400, 19px/1.62 |
| Body | Archivo 400, 17px/1.68 |
| Body S | Archivo 400, 15–16px/1.6 |
| Кикер | IBM Plex Mono 500, 10px, ls .22em, uppercase |
| Мета / лейбл | IBM Plex Mono 500, 10–11px, ls .16–.18em, uppercase |
| Nav / кнопка | IBM Plex Mono 500, 11–12px, ls .1–.12em, uppercase |
| Email | IBM Plex Mono 500, 20px |

**Отступы**: шаг 4px. Ходовые значения: 3, 6, 10, 12, 14, 16, 20, 22, 24, 26, 28, 32, 44, 48, 56, 64, 80, 84, 96, 112.
**Радиусы**: 0 везде — намеренно, часть стиля.
**Тени**: нет. Глубина строится хайрлайнами и `#F7F6F4`.
**Ширины**: контейнер 1080px; текстовые колонки 560–620px; hero 820px.
**Easing**: `cubic-bezier(.16,1,.3,1)` (появление), `steps(1)` (каретка).

## Assets
Изображений и иконок нет. Единственные графические элементы — символы «→» и «▍», текстовые. Шрифты грузятся с Google Fonts (в проде — self-host, `font-display:swap`, подмножество latin + cyrillic).

## Files
- `Zatinatscky Site.dc.html` — весь дизайн: четыре раздела × два языка, шапка, футер, вся логика навигации и локали.
- `support.js` — рантайм прототипа. Продакшену не нужен; включён только чтобы файл открывался в браузере.
