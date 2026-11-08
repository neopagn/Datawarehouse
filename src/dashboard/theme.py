"""Visual layer only: page CSS and small HTML figures. Holds no data logic."""
from html import escape


CSS = """
<style>
:root {
  --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6d68;
  --line: #e4e3dc; --surface: #ffffff; --accent: #2a78d6;
}
html, body, [data-testid="stApp"], [data-testid="stSidebar"], button, input {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
.block-container { max-width: 1180px; padding-top: 2.4rem; padding-bottom: 4rem; }

/* Header: the screen name is secondary to the finding underneath it. */
.eyebrow {
  font-size: .74rem; font-weight: 600; letter-spacing: .09em; text-transform: uppercase;
  color: var(--ink-3); margin-bottom: .1rem;
}
[data-testid="stHeading"] h2 {
  font-size: 1.05rem; font-weight: 600; color: var(--ink-2); padding: 0 0 .15rem 0;
}
[data-testid="stHeading"] h3 {
  font-size: 1.12rem; font-weight: 650; padding: 0 0 .1rem 0; letter-spacing: -.005em;
}
.insight {
  font-size: 1.72rem; line-height: 1.26; font-weight: 650; letter-spacing: -.018em;
  color: var(--ink); max-width: 44rem; margin: .05rem 0 .9rem 0;
}

/* KPI tiles */
[data-testid="stMetric"] {
  background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  padding: .85rem 1rem .8rem 1rem;
}
[data-testid="stMetricLabel"] p { font-size: .8rem; color: var(--ink-2); }
[data-testid="stMetricValue"] { font-size: 1.75rem; font-weight: 650; letter-spacing: -.015em; }

/* Bordered containers act as chart cards. */
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {
  border-color: var(--line) !important; border-radius: 12px !important; background: var(--surface);
}
[data-testid="stExpander"] details { border-color: var(--line); border-radius: 10px; background: var(--surface); }
[data-testid="stExpander"] summary p { font-size: .82rem; color: var(--ink-2); }

/* Caveats stay visible but quiet: a hairline note, not a coloured banner. */
[data-testid="stAlert"] > div {
  background: transparent !important; border: 0 !important; border-left: 3px solid #c3c2b7 !important;
  border-radius: 0 !important; padding: .1rem 0 .1rem .8rem !important; min-height: 0 !important;
}
[data-testid="stAlert"] p { font-size: .82rem !important; line-height: 1.45; color: var(--ink-2) !important; }
[data-testid="stAlertContentWarning"], [data-testid="stAlertContentInfo"] { color: var(--ink-2); }
[data-testid="stAlert"] svg { display: none; }
.stAlert:has([data-testid="stAlertContentError"]) > div { border-left-color: #d03b3b !important; }
[data-testid="stCaptionContainer"] { opacity: 1; }
[data-testid="stCaptionContainer"] p { color: var(--ink-3); font-size: .8rem; line-height: 1.45; }

/* Sidebar: the screen radio reads as a navigation list. */
[data-testid="stSidebar"] { background: #fbfbf9; border-right: 1px solid var(--line); }
.brand { font-size: 1.02rem; font-weight: 700; letter-spacing: -.01em; color: var(--ink); line-height: 1.25; margin-bottom: 1rem; }
.brand small { display: block; font-size: .76rem; font-weight: 400; letter-spacing: 0; color: var(--ink-3); margin-top: .15rem; }
[data-testid="stSidebar"] [data-testid="stRadioOption"] {
  padding: .42rem .65rem; margin: 0; border-radius: 7px; width: 100%; cursor: pointer;
}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover { background: #f0efea; }
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] { background: #e3eefb; }
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p { font-weight: 650; color: #104281; }
[data-testid="stSidebar"] [data-testid="stRadioOption"] > span + div > div:first-child { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: .12rem; margin-bottom: .9rem; }

/* HTML figures */
.seg { display: flex; gap: 2px; height: 28px; margin: .35rem 0 .55rem 0; }
.seg > div {
  display: flex; align-items: center; padding-left: .55rem; border-radius: 4px; min-width: 0;
  font-size: .8rem; font-weight: 600; white-space: nowrap; overflow: hidden;
}
.key { display: flex; flex-wrap: wrap; gap: .25rem 1.15rem; font-size: .8rem; color: var(--ink-2); margin-bottom: .2rem; }
.key i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: .38rem; }
.foot { margin-top: 2.2rem; padding-top: .5rem; border-top: 1px solid var(--line); }
</style>
"""


def apply():
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)


def brand():
    return '<div class="brand">OULAD Analytics<small>Kho dữ liệu học tập · CO4031</small></div>'


def eyebrow(text):
    return f'<div class="eyebrow">{escape(text)}</div>'


def insight(text):
    return f'<div class="insight">{escape(text)}</div>'


def segmented_bar(parts):
    """Whole-split figure. parts: (name, count, fill, label ink); zero parts draw nothing."""
    parts = [part for part in parts if part[1]]
    total = sum(part[1] for part in parts)
    if not total:
        return ''
    blocks, key = [], []
    for name, count, fill, ink in parts:
        share = 100 * count / total
        # A block too narrow for its label prints none; the value stays in the legend.
        text = f'{share:.1f}%' if share >= 7 else ''
        blocks.append(f'<div style="flex:{count} 1 0;background:{fill};color:{ink}" '
                      f'title="{escape(name)}: {count:,} ({share:.1f}%)">{text}</div>')
        key.append(f'<span><i style="background:{fill}"></i>{escape(name)} · {count:,}</span>')
    return f'<div class="seg">{"".join(blocks)}</div><div class="key">{"".join(key)}</div>'
