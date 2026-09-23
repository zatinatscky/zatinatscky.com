"""Генерация Canvas (.canvas.tsx) из результатов разбора.

Эмитим самодостаточный React-файл в том же формате, что и ручные разборы:
текст с подсветкой цепочек + строка IPA под каждой строкой + таблица цепочек +
график самых длинных цепочек.
"""

from __future__ import annotations

import json

from .models import Block, Chain, Token
from .text_display import token_displays_for_output


def _js(s: str) -> str:
    """Безопасный JS/TS-строковый литерал (JSON-строка — валидный JS)."""
    return json.dumps(s, ensure_ascii=False)


def _emit_segs(tokens: list[Token], use_ipa: bool) -> str:
    """Строит JS-массив сегментов строки: P("..") / C("..","cid",true)."""
    parts: list[str] = []
    plain = ""

    def flush() -> None:
        nonlocal plain
        if plain:
            parts.append(f"P({_js(plain)})")
            plain = ""

    displays = token_displays_for_output(tokens) if not use_ipa else None

    for i, tok in enumerate(tokens):
        if tok.is_word and tok.chain:
            flush()
            text = tok.ipa if use_ipa else displays[i]
            if tok.internal:
                parts.append(f"C({_js(text)}, {_js(tok.chain)}, true)")
            else:
                parts.append(f"C({_js(text)}, {_js(tok.chain)})")
        else:
            # обычное слово или разделитель -> в текст (для IPA берём транскрипцию слова)
            plain += tok.ipa if (use_ipa and tok.is_word) else (displays[i] if displays is not None else tok.display)
    flush()
    return "[" + ", ".join(parts) + "]"


def _chain_ids_in_block(block: Block) -> list[str]:
    """Список id цепочек, встречающихся в блоке (по порядку появления)."""
    seen: list[str] = []
    for line in block.lines:
        for tok in line.words():
            if tok.chain and tok.chain not in seen:
                seen.append(tok.chain)
    return seen


def _member_counts(blocks: list[Block]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        for line in block.lines:
            for tok in line.words():
                if tok.chain:
                    counts[tok.chain] = counts.get(tok.chain, 0) + 1
    return counts


def generate(blocks: list[Block], chains: list[Chain], title: str, source: str) -> str:
    """Возвращает полный текст .canvas.tsx."""
    counts = _member_counts(blocks)

    # --- CHAINS ---
    chain_lines = []
    for c in chains:
        chain_lines.append(
            "  { "
            f"id: {_js(c.id)}, color: PAL.{c.color}, sound: {_js(c.sound)}, "
            f"words: {_js(c.words)}, lines: {_js(c.lines)}, kind: {_js(c.kind)} "
            "},"
        )
    chains_ts = "\n".join(chain_lines)

    # --- SECTIONS ---
    section_blocks = []
    for block in blocks:
        ids = _chain_ids_in_block(block)
        line_entries = []
        for line in block.lines:
            segs = _emit_segs(line.tokens, use_ipa=False)
            phon = _emit_segs(line.tokens, use_ipa=True)
            line_entries.append(f"      {{ n: {line.no}, segs: {segs}, phon: {phon} }},")
        section_blocks.append(
            "  {\n"
            f"    title: {_js(block.title)},\n"
            f"    chainIds: {json.dumps(ids, ensure_ascii=False)},\n"
            "    lines: [\n" + "\n".join(line_entries) + "\n    ],\n"
            "  },"
        )
    sections_ts = "\n".join(section_blocks)

    # --- Метрики ---
    n_chains = len(chains)
    n_multi = sum(1 for c in chains if "многослож" in c.kind.lower())
    n_internal = sum(1 for c in chains if "внутр" in c.kind.lower())
    n_words = sum(counts.values())

    # --- График: топ цепочек по числу слов ---
    top = sorted(chains, key=lambda c: counts.get(c.id, 0), reverse=True)[:6]
    cats = [f"{c.sound} — {counts.get(c.id, 0)}" for c in top]
    data = [counts.get(c.id, 0) for c in top]
    chart_cats = json.dumps(cats, ensure_ascii=False)
    chart_data = json.dumps(data)

    tpl = _TEMPLATE
    tpl = tpl.replace("/*TITLE*/", _js(title))
    tpl = tpl.replace("/*SOURCE*/", _js(source))
    tpl = tpl.replace("/*CHAINS*/", chains_ts)
    tpl = tpl.replace("/*SECTIONS*/", sections_ts)
    tpl = tpl.replace("/*N_CHAINS*/", str(n_chains))
    tpl = tpl.replace("/*N_MULTI*/", str(n_multi))
    tpl = tpl.replace("/*N_INTERNAL*/", str(n_internal))
    tpl = tpl.replace("/*N_WORDS*/", str(n_words))
    tpl = tpl.replace("/*CHART_CATS*/", chart_cats)
    tpl = tpl.replace("/*CHART_DATA*/", chart_data)
    return tpl


# Статический шаблон Canvas. Плейсхолдеры /*...*/ заполняются выше.
_TEMPLATE = r"""// АВТОСГЕНЕРИРОВАНО rhyme_analyzer. Не редактировать вручную — перегенерируется.
// Цвет = звуковая цепочка; пунктир = созвучие внутри строки; вторая строка = IPA.

import {
  Stack, H1, H2, Text, Card, CardHeader, CardBody, Grid, Stat, Table,
  BarChart, Callout, Divider, Row, colorPalette, useHostTheme,
} from "cursor/canvas";

type Seg = { t: string; chain?: string; internal?: boolean };
type Line = { n: number; segs: Seg[]; phon: Seg[] };
type Chain = { id: string; color: string; sound: string; words: string; lines: string; kind: string };

const P = (t: string): Seg => ({ t });
const C = (t: string, chain: string, internal?: boolean): Seg => ({ t, chain, internal });

const PAL = {
  purple: colorPalette.purple,
  green: colorPalette.green,
  blue: colorPalette.blue,
  orange: colorPalette.orange,
  pink: colorPalette.pink,
};

const CHAINS: Chain[] = [
/*CHAINS*/
];
const CHAIN_MAP = new Map(CHAINS.map((c) => [c.id, c]));

type Section = { title: string; chainIds: string[]; lines: Line[] };
const SECTIONS: Section[] = [
/*SECTIONS*/
];

function colorOf(id?: string): string | undefined {
  return id ? CHAIN_MAP.get(id)?.color : undefined;
}

function renderSegs(segs: Seg[], italic: boolean) {
  return segs.map((s, i) => {
    const color = colorOf(s.chain);
    if (!color) return <span key={i}>{s.t}</span>;
    return (
      <span key={i} style={{ color, fontWeight: 600, fontStyle: italic ? "italic" : undefined,
        textDecoration: s.internal ? "underline dotted" : undefined, textUnderlineOffset: 3 }}>
        {s.t}
      </span>
    );
  });
}

function LyricLine({ n, segs, phon }: Line) {
  const theme = useHostTheme();
  return (
    <div style={{ padding: "4px 0", borderBottom: `1px solid ${theme.stroke.tertiary}` }}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
        <span style={{ color: theme.text.quaternary, fontSize: 11, width: 24, textAlign: "right",
          flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>{n}</span>
        <span style={{ color: theme.text.primary, fontSize: 14, lineHeight: "22px" }}>{renderSegs(segs, false)}</span>
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline", marginTop: 1 }}>
        <span style={{ width: 24, flexShrink: 0, textAlign: "right", color: theme.text.quaternary, fontSize: 11 }}>→</span>
        <span style={{ color: theme.text.tertiary, fontSize: 12.5, lineHeight: "18px", fontStyle: "italic" }}>{renderSegs(phon, true)}</span>
      </div>
    </div>
  );
}

function ChainLegend({ chainIds }: { chainIds: string[] }) {
  return (
    <Row gap={8} wrap>
      {chainIds.map((id) => {
        const c = CHAIN_MAP.get(id);
        if (!c) return null;
        return <span key={id} style={{ color: c.color, fontWeight: 600, fontSize: 12.5, whiteSpace: "nowrap" }} title={c.words}>{c.sound}</span>;
      })}
    </Row>
  );
}

function Legend() {
  return (
    <Row gap={18} wrap align="center">
      <Row gap={6} align="center">
        <span style={{ color: PAL.green, fontWeight: 700, fontSize: 14 }}>Слово</span>
        <Text size="small" tone="secondary">— цвет = звуковая цепочка</Text>
      </Row>
      <Row gap={6} align="center">
        <span style={{ color: PAL.green, fontWeight: 700, fontSize: 14, textDecoration: "underline dotted", textUnderlineOffset: 3 }}>Слово</span>
        <Text size="small" tone="secondary">— созвучие внутри строки</Text>
      </Row>
      <Text size="small" tone="secondary">→ строка снизу — транскрипция IPA</Text>
    </Row>
  );
}

export default function RhymeAnalysis() {
  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 940 }}>
      <Stack gap={6}>
        <H1>{/*TITLE*/}</H1>
        <Text tone="secondary">Автоматический фонетический разбор рифм. Источник: <Text as="span" weight="medium">{/*SOURCE*/}</Text></Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value={`${/*N_CHAINS*/}`} label="звуковые цепочки" />
        <Stat value={`${/*N_WORDS*/}`} label="созвучных слов" tone="info" />
        <Stat value={`${/*N_MULTI*/}`} label="многосложные" tone="success" />
        <Stat value={`${/*N_INTERNAL*/}`} label="с внутр. рифмой" tone="warning" />
      </Grid>

      <Stack gap={10}>
        <H2>Текст с подсветкой и транскрипцией</H2>
        <Legend />
        <Card>
          <CardBody style={{ padding: 16 }}>
            <Stack gap={16}>
              {SECTIONS.map((sec) => (
                <Stack key={sec.title} gap={6}>
                  <Text size="small" tone="tertiary" weight="semibold" style={{ textTransform: "uppercase", letterSpacing: 0.5 }}>{sec.title}</Text>
                  <ChainLegend chainIds={sec.chainIds} />
                  <Stack gap={0} style={{ marginTop: 4 }}>
                    {sec.lines.map((ln) => (<LyricLine key={ln.n} n={ln.n} segs={ln.segs} phon={ln.phon} />))}
                  </Stack>
                </Stack>
              ))}
            </Stack>
          </CardBody>
        </Card>
      </Stack>

      <Stack gap={8}>
        <H2>Карта звуковых цепочек</H2>
        <Table
          headers={["Звук", "Слова", "Строки", "Тип"]}
          columnAlign={["left", "left", "left", "left"]}
          rows={CHAINS.map((c) => [<span style={{ color: c.color, fontWeight: 600 }}>{c.sound}</span>, c.words, c.lines, c.kind])}
          striped
        />
      </Stack>

      <Stack gap={8}>
        <H2>Самые длинные цепочки (число созвучных слов)</H2>
        <BarChart horizontal categories={/*CHART_CATS*/} series={[{ name: "Созвучных слов", data: /*CHART_DATA*/ }]} height={240} />
        <Text size="small" tone="tertiary">Подписи (число слов) указаны в категориях.</Text>
      </Stack>

      <Divider />

      <Callout tone="neutral" title="Как получено">
        <Text size="small">
          Пайплайн rhyme_analyzer: чистка текста → нормализация (числа/латиница → произношение) →
          G2P/IPA с ударениями → рифменные хвосты (от ударной гласной) → группировка по фонетической
          близости в цепочки. Транскрипция под строками — IPA.
        </Text>
      </Callout>
    </Stack>
  );
}
"""
