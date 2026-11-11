#!/usr/bin/env python3
"""Build the README / social images: python3 docs/images/src/build.py  (needs Google Chrome).
Writes docs/images/{before-after,architecture}.{en,ja}.png from the HTML below."""
import os, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
W, H = 1600, 900

T = {
 "en": dict(
  font='-apple-system, "Helvetica Neue", Arial, sans-serif',
  ba_title="AI agents that pass work to each other, without you in the middle",
  before="Usually", after="With agent-doorbell",
  b1="You relay everything", b1s="You become the message bus.", you="you",
  b2="Every agent polls on a schedule", b2s="Each check is a model run, even when nothing is there.",
  a1="Messages wait in a shared inbox", a1s="send · inbox · ack, over MCP or a tiny CLI",
  a2="Only a new message wakes an agent", a2s="Idle: zero model usage.",
  run="model run", msg="message arrives", inbox="inbox",
  agent_a="agent A", agent_b="agent B",
  foot="github.com/Jaga-Studio/agent-doorbell · MIT · git clone … && ./setup.sh",
  ar_title="How agent-doorbell works",
  c1="Hosted assistant", c1s="custom MCP connector<br>checks its inbox on its own<br>no bell needed", c1e="tested with Muse",
  c2="Webhook-routine agent", c2s="connects over MCP<br>woken by a webhook", c2e="tested with Grok Bot",
  c3="Claude Code / CLI agent", c3s="doorbell CLI<br>woken over SSH<br>(one fixed command only)", c3e="tested with Claude Code",
  region="One always-on machine on your tailnet (Mac mini, Linux, NAS). Nothing public.",
  bus_s="MCP server: send · inbox · ack<br>tokens stored as hashes only",
  bell_s="watches the inbox, no AI<br>wakes each agent once per batch<br>daily cap",
  l_read="reads (read-only)", l_talk="send / inbox / ack", l_wake="wake-up (on arrival only)",
 ),
 "ja": dict(
  font='"Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif',
  ba_title="AI エージェントどうしの受け渡しを、人が間に入らずに",
  before="よくあるやり方", after="agent-doorbell なら",
  b1="人が全部伝言する", b1s="自分がメッセージ係になってしまう", you="あなた",
  b2="全員が定時に見に行く", b2s="何も無くても、見に行くたびに AI の使用量が減る",
  a1="メッセージは共有の受信箱で待つ", a1s="MCP か小さな CLI で send・inbox・ack",
  a2="届いたときだけ、呼び鈴が相手を 1 回起こす", a2s="何も無い間の AI 使用量はゼロ",
  run="AI が動く", msg="メッセージ到着", inbox="受信箱",
  agent_a="エージェント A", agent_b="エージェント B",
  foot="github.com/Jaga-Studio/agent-doorbell · MIT · git clone … && ./setup.sh",
  ar_title="agent-doorbell のしくみ",
  c1="ホスト型アシスタント", c1s="MCP コネクタでつなぐ<br>自分で受信箱を見回る<br>呼び鈴は不要", c1e="Muse で確認",
  c2="Webhook ルーティン", c2s="MCP でつなぐ<br>Webhook で起こす", c2e="Grok Bot で確認",
  c3="Claude Code など CLI", c3s="doorbell CLI でつなぐ<br>SSH で起こす<br>（決まったコマンドだけ）", c3e="Claude Code で確認",
  region="tailnet の中の常時起動の機械 1 台（Mac mini・Linux・NAS）。外には公開しない",
  bus_s="MCP サーバー：send・inbox・ack<br>トークンはハッシュだけ保存",
  bell_s="受信箱を見張る（AI は使わない）<br>まとめて 1 回だけ起こす<br>1 日の上限つき",
  l_read="読むだけ", l_talk="send・inbox・ack", l_wake="起こす（届いたときだけ）",
 ),
}

BELL = ('<svg viewBox="0 0 24 24" width="{s}" height="{s}" fill="#E8890C"><path d="M12 2a1.5 1.5 0 0 1 1.5 1.5v.6A6.5 6.5 0 0 1 18.5 '
        '10.5v4.2l1.8 2.4a.8.8 0 0 1-.6 1.3H4.3a.8.8 0 0 1-.6-1.3l1.8-2.4v-4.2A6.5 6.5 0 0 1 10.5 4.1v-.6A1.5 1.5 0 0 1 12 2zm-2.4 '
        '17.6h4.8a2.4 2.4 0 0 1-4.8 0z"/></svg>')

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:%dpx;height:%dpx;background:#F6F5F1;color:#1F2328;font-family:%s;overflow:hidden}
.title{font-size:46px;font-weight:700;letter-spacing:-.5px;padding:54px 70px 0}
.foot{position:absolute;left:70px;right:70px;bottom:34px;font-size:22px;color:#6B6F76;display:flex;justify-content:space-between}
.foot b{color:#1F2328}
.pill{display:inline-block;padding:7px 14px;border-radius:999px;background:#fff;border:2px solid #D0D3D8;font-size:21px;font-weight:600;white-space:nowrap}
.row{display:flex;align-items:center;flex-wrap:nowrap}
.arrow{color:#9AA0A6;font-size:28px;margin:0 8px}
"""

def timeline(active_all, lang):
    t = T[lang]
    dots = []
    for i in range(12):
        hit = i == 7
        on = active_all or hit
        style = ("background:#E8890C;border-color:#E8890C" if on else "background:transparent;border-color:#C5C9CF")
        dots.append(f'<span style="display:inline-block;width:26px;height:26px;border-radius:50%;border:3px solid;{style};margin-right:12px;position:relative">'
                    + ('<span style="position:absolute;top:-34px;left:50%;transform:translateX(-50%);font-size:24px">✉︎</span>' if hit else '') + '</span>')
    legend = (f'<div style="font-size:19px;color:#6B6F76;margin-top:12px"><span style="color:#E8890C">●</span> {t["run"]}'
              f' &nbsp; ✉︎ {t["msg"]}</div>')
    return f'<div style="margin-top:46px">{"".join(dots)}</div>{legend}'

def before_after(lang):
    t = T[lang]
    card = 'background:#fff;border-radius:22px;padding:30px 34px;height:262px;box-shadow:0 2px 0 #E4E2DC'
    h = 'font-size:30px;font-weight:700;margin-bottom:8px'
    s = 'font-size:22px;color:#555A61'
    a, b = t["agent_a"], t["agent_b"]
    left = f'''
      <div style="font-size:24px;font-weight:700;color:#B4462F;margin-bottom:16px">✕ {t["before"]}</div>
      <div style="{card};margin-bottom:22px"><div style="{h}">{t["b1"]}</div><div style="{s}">{t["b1s"]}</div>
        <div class="row" style="margin-top:34px"><span class="pill">{a}</span><span class="arrow">→</span><span class="pill" style="border-color:#B4462F;color:#B4462F">{t["you"]}</span><span class="arrow">→</span><span class="pill">{b}</span></div></div>
      <div style="{card}"><div style="{h}">{t["b2"]}</div><div style="{s}">{t["b2s"]}</div>{timeline(True, lang)}</div>'''
    right = f'''
      <div style="font-size:24px;font-weight:700;color:#2E7D4F;margin-bottom:16px">✓ {t["after"]}</div>
      <div style="{card};margin-bottom:22px;outline:3px solid #2E7D4F"><div style="{h}">{t["a1"]}</div><div style="{s}">{t["a1s"]}</div>
        <div class="row" style="margin-top:34px"><span class="pill">{a}</span><span class="arrow">→</span><span class="pill" style="border-color:#2F6FEB;color:#2F6FEB">{t["inbox"]}</span><span class="arrow">→</span>{BELL.format(s=34)}<span class="arrow">→</span><span class="pill">{b}</span></div></div>
      <div style="{card};outline:3px solid #2E7D4F"><div style="{h}">{t["a2"]}</div><div style="{s}">{t["a2s"]}</div>{timeline(False, lang)}</div>'''
    body = f'''<div class="title">{t["ba_title"]}</div>
      <div style="display:flex;gap:40px;padding:34px 70px 0">
        <div style="flex:1">{left}</div><div style="flex:1">{right}</div></div>
      <div class="foot"><span><b>agent-doorbell</b> &nbsp;{BELL.format(s=22)}</span><span>{t["foot"]}</span></div>'''
    return body

def architecture(lang):
    t = T[lang]
    def card(x, title, sub, eg):
        return (f'<div style="position:absolute;left:{x}px;top:150px;width:420px;height:200px;background:#fff;border-radius:22px;'
                f'padding:24px 28px;box-shadow:0 2px 0 #E4E2DC"><div style="font-size:28px;font-weight:700">{title}</div>'
                f'<div style="font-size:20px;color:#555A61;margin-top:8px;line-height:1.45">{sub}</div>'
                f'<div style="position:absolute;right:22px;bottom:16px;font-size:17px;color:#8A8F96">{eg}</div></div>')
    def box(x, color, name, sub, icon=""):
        return (f'<div style="position:absolute;left:{x}px;top:520px;width:460px;height:190px;background:#fff;border-radius:22px;'
                f'border:4px solid {color};padding:24px 30px"><div style="font-size:34px;font-weight:800;color:{color};display:flex;align-items:center;gap:10px">{icon}{name}</div>'
                f'<div style="font-size:20px;color:#555A61;margin-top:8px;line-height:1.45">{sub}</div></div>')
    lab = lambda x, y, txt, c="#6B6F76": f'<div style="position:absolute;left:{x}px;top:{y}px;font-size:20px;font-weight:700;color:{c};background:#F6F5F1;padding:2px 8px">{txt}</div>'
    svg = f'''<svg width="{W}" height="{H}" style="position:absolute;left:0;top:0">
      <defs><marker id="g" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#7C828A"/></marker>
            <marker id="o" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#E8890C"/></marker></defs>
      <rect x="60" y="440" width="1480" height="330" rx="26" fill="none" stroke="#B9BDC3" stroke-width="3" stroke-dasharray="12 10"/>
      <path d="M300 352 L420 516" stroke="#7C828A" stroke-width="4" fill="none" marker-start="url(#g)" marker-end="url(#g)"/>
      <path d="M720 352 L520 516" stroke="#7C828A" stroke-width="4" fill="none" marker-start="url(#g)" marker-end="url(#g)"/>
      <path d="M1170 352 L620 516" stroke="#7C828A" stroke-width="4" fill="none" marker-start="url(#g)" marker-end="url(#g)"/>
      <path d="M940 615 L 640 615" stroke="#7C828A" stroke-width="4" fill="none" stroke-dasharray="8 7" marker-end="url(#g)"/>
      <path d="M1060 516 L930 356" stroke="#E8890C" stroke-width="5" fill="none" stroke-dasharray="14 9" marker-end="url(#o)"/>
      <path d="M1300 516 L1330 356" stroke="#E8890C" stroke-width="5" fill="none" stroke-dasharray="14 9" marker-end="url(#o)"/>
      <line x1="890" y1="742" x2="950" y2="742" stroke="#7C828A" stroke-width="4"/>
      <line x1="1150" y1="742" x2="1210" y2="742" stroke="#E8890C" stroke-width="5" stroke-dasharray="14 9"/>
    </svg>'''
    body = f'''<div class="title">{t["ar_title"]}</div>{svg}
      {card(80, t["c1"], t["c1s"], t["c1e"])}{card(590, t["c2"], t["c2s"], t["c2e"])}{card(1100, t["c3"], t["c3s"], t["c3e"])}
      {box(170, "#2F6FEB", "bus", t["bus_s"])}{box(950, "#E8890C", "bell", t["bell_s"], BELL.format(s=36))}
      <div style="position:absolute;left:90px;top:728px;font-size:19px;color:#6B6F76;max-width:780px">{t["region"]}</div>
      {lab(665, 575, t["l_read"])}
      <div style="position:absolute;left:962px;top:728px;font-size:19px;color:#555A61">{t["l_talk"]}</div>
      <div style="position:absolute;left:1222px;top:728px;font-size:19px;color:#C26F00">{t["l_wake"]}</div>
      <div class="foot"><span><b>agent-doorbell</b></span><span>{t["foot"]}</span></div>'''
    return body

def render(name, lang, body):
    html = f'<!doctype html><html lang="{lang}"><meta charset="utf-8"><style>{CSS % (W, H, T[lang]["font"])}</style><body style="position:relative">{body}</body></html>'
    src = os.path.join(HERE, f"{name}.{lang}.html")
    with open(src, "w", encoding="utf-8") as f:
        f.write(html)
    png = os.path.join(OUT, f"{name}.{lang}.png")
    for attempt in range(3):  # headless Chrome now and then exits early; retry
        r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                            "--user-data-dir=" + tempfile.mkdtemp(), f"--window-size={W},{H}", f"--screenshot={png}", "file://" + src],
                           capture_output=True, text=True, cwd=tempfile.gettempdir())
        if r.returncode == 0:
            break
    else:
        raise SystemExit(f"chrome failed for {png}: {r.stderr[-500:]}")
    print(png)

for lang in ("en", "ja"):
    render("before-after", lang, before_after(lang))
    render("architecture", lang, architecture(lang))
