"""Portable exports for sharing a :class:`~skill_anything.models.SkillPack`.

The web export is deliberately a single, dependency-free HTML file. It can be
opened from disk, attached to an email, or hosted on GitHub Pages without a
build step. The Anki export uses tab-separated UTF-8 text, which Anki imports
without an additional Python package.
"""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from skill_anything.models import SkillPack, slugify


class AnkiExporter:
    """Export flashcards and quiz questions as an Anki-compatible TSV file."""

    def export(self, pack: SkillPack, output_dir: str | Path) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{slugify(pack.title)}-anki.tsv"
        topic_tag = self._tag(slugify(pack.title))

        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("#separator:Tab\n")
            handle.write("#html:true\n")
            handle.write("#columns:Front\tBack\tTags\n")
            handle.write("#tags column:3\n")
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")

            for card in pack.flashcards:
                tags = ["skill-anything", topic_tag, "flashcard"]
                tags.extend(self._tag(tag) for tag in card.tags)
                writer.writerow(
                    [
                        self._html(card.front),
                        self._html(card.back),
                        " ".join(dict.fromkeys(filter(None, tags))),
                    ]
                )

            for question in pack.quiz_questions:
                front = self._html(question.question)
                if question.options:
                    front += "<br><br>" + "<br>".join(
                        self._html(option) for option in question.options
                    )
                back = f"<strong>Answer:</strong> {self._html(question.answer)}"
                if question.explanation:
                    back += f"<br><br>{self._html(question.explanation)}"
                tags = [
                    "skill-anything",
                    topic_tag,
                    "quiz",
                    self._tag(question.difficulty.value),
                    self._tag(question.question_type.value),
                ]
                writer.writerow([front, back, " ".join(filter(None, tags))])

        return path

    @staticmethod
    def _html(value: str) -> str:
        return html.escape(str(value), quote=False).replace("\n", "<br>")

    @staticmethod
    def _tag(value: str) -> str:
        return "-".join(value.strip().lower().split()).replace("_", "-")


class WebExporter:
    """Export a study pack as a self-contained interactive learning site."""

    def export(self, pack: SkillPack, output_dir: str | Path) -> Path:
        site_dir = Path(output_dir) / f"{slugify(pack.title)}-site"
        site_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(pack.to_dict(), ensure_ascii=False, separators=(",", ":"))
        # Prevent source text from escaping the application/json script tag.
        payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        page = (
            _PAGE.replace("__PACK_JSON__", payload)
            .replace("__PACK_TITLE__", html.escape(pack.title, quote=True))
            .replace("__GENERATED_DATE__", generated)
        )
        index = site_dir / "index.html"
        index.write_text(page, encoding="utf-8")
        return index


_PAGE = r'''<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Interactive study pack for __PACK_TITLE__">
  <title>__PACK_TITLE__ · Skill-Anything</title>
  <style>
    :root{--bg:#f6f7fb;--card:#fff;--text:#172033;--muted:#687085;--line:#e5e8f0;--brand:#6557e8;--brand2:#16a6a1;--good:#138a5b;--shadow:0 12px 36px rgba(32,37,63,.09)}
    [data-theme="dark"]{--bg:#10121a;--card:#191c27;--text:#edf0f7;--muted:#9ba4b8;--line:#2d3242;--brand:#978cff;--brand2:#3bd1c9;--good:#42d397;--shadow:0 14px 40px rgba(0,0,0,.3)}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}button,input{font:inherit}button{cursor:pointer}
    .shell{width:min(1160px,calc(100% - 32px));margin:auto}.hero{padding:58px 0 24px;background:radial-gradient(circle at 10% 0,rgba(101,87,232,.16),transparent 34%),radial-gradient(circle at 88% 12%,rgba(22,166,161,.14),transparent 30%)}
    .topbar{display:flex;justify-content:space-between;gap:16px;align-items:center}.brand{font-weight:800;letter-spacing:-.02em}.brand span{color:var(--brand)}.actions{display:flex;gap:8px;flex-wrap:wrap}.icon-btn,.action{border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:12px;padding:9px 13px}.action.primary{border-color:var(--brand);background:var(--brand);color:white}
    h1{font-size:clamp(2.2rem,6vw,4.6rem);line-height:1.02;max-width:900px;margin:54px 0 18px;letter-spacing:-.055em}.subtitle{color:var(--muted);max-width:760px;font-size:1.08rem}.meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.pill{background:var(--card);border:1px solid var(--line);padding:6px 11px;border-radius:999px;color:var(--muted);font-size:.88rem}
    .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:30px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:var(--shadow)}.stat strong{display:block;font-size:1.65rem;line-height:1.1}.stat span{color:var(--muted);font-size:.86rem}
    .toolbar{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);padding:12px 0}.toolbar-inner{display:flex;gap:10px;align-items:center}.tabs{display:flex;gap:6px;overflow:auto;flex:1;scrollbar-width:none}.tab{white-space:nowrap;border:0;background:transparent;color:var(--muted);padding:9px 12px;border-radius:10px}.tab.active{background:var(--card);color:var(--brand);box-shadow:0 3px 12px rgba(0,0,0,.06);font-weight:700}.search{width:min(260px,30vw);border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:11px;padding:9px 12px}
    main{padding:30px 0 70px}.panel{display:none}.panel.active{display:block}.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:clamp(18px,3vw,32px);box-shadow:var(--shadow);margin-bottom:16px}.card h2,.card h3{line-height:1.2;letter-spacing:-.025em}.prose{max-width:900px}.prose h2{margin-top:1.8em}.concept-grid,.glossary-grid,.exercise-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.concept{border-left:4px solid var(--brand)}.muted{color:var(--muted)}
    .quiz-card{max-width:820px;margin:auto}.quiz-head{display:flex;justify-content:space-between;color:var(--muted);font-size:.9rem}.options{display:grid;gap:9px;margin:20px 0}.option{border:1px solid var(--line);background:var(--bg);color:var(--text);text-align:left;border-radius:12px;padding:12px 14px}.answer{display:none;border-left:4px solid var(--good);padding:12px 16px;background:color-mix(in srgb,var(--good) 9%,var(--card));border-radius:8px}.answer.show{display:block}.controls{display:flex;gap:9px;flex-wrap:wrap;margin-top:20px}.progress{height:7px;background:var(--line);border-radius:999px;overflow:hidden;margin:14px 0 24px}.progress>i{display:block;height:100%;background:linear-gradient(90deg,var(--brand),var(--brand2));transition:width .25s}
    .flash-wrap{max-width:760px;margin:auto}.flashcard{height:320px;perspective:1000px;cursor:pointer}.flash-inner{height:100%;position:relative;transition:transform .45s;transform-style:preserve-3d}.flashcard.flipped .flash-inner{transform:rotateY(180deg)}.face{position:absolute;inset:0;display:grid;place-items:center;text-align:center;padding:40px;background:var(--card);border:1px solid var(--line);border-radius:22px;backface-visibility:hidden;box-shadow:var(--shadow);font-size:clamp(1.25rem,3vw,2rem)}.back{transform:rotateY(180deg);border-color:var(--brand2)}
    .tag{display:inline-block;padding:3px 8px;border-radius:999px;background:color-mix(in srgb,var(--brand) 12%,var(--card));color:var(--brand);font-size:.78rem;margin:2px}.empty{text-align:center;color:var(--muted);padding:50px}.footer{text-align:center;color:var(--muted);padding:35px;border-top:1px solid var(--line)}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-size:.82rem;text-transform:uppercase}
    @media(max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}.concept-grid,.glossary-grid,.exercise-grid{grid-template-columns:1fr}.search{display:none}.hero{padding-top:28px}h1{margin-top:34px}.topbar{align-items:flex-start}.hide-mobile{display:none}}
    @media print{.toolbar,.actions,.controls,.footer{display:none!important}.panel{display:block!important}.card{box-shadow:none;break-inside:avoid}.hero{padding:20px 0}.flashcard{height:auto}.face{position:relative;min-height:120px}.back{transform:none;margin-top:8px}.flash-inner{transform:none!important}}
  </style>
</head>
<body>
  <header class="hero"><div class="shell">
    <div class="topbar"><div class="brand">Skill<span>Anything</span> 🌈</div><div class="actions"><button class="icon-btn" id="theme" aria-label="Toggle theme">◐</button><button class="action hide-mobile" id="download">↓ JSON</button><button class="action" onclick="window.print()">Print</button></div></div>
    <h1 id="title"></h1><p class="subtitle" id="summary"></p><div class="meta" id="meta"></div><div class="stats" id="stats"></div>
  </div></header>
  <nav class="toolbar"><div class="shell toolbar-inner"><div class="tabs" id="tabs"></div><input class="search" id="search" type="search" placeholder="Search this pack…" aria-label="Search"></div></nav>
  <main class="shell">
    <section class="panel active" data-panel="overview"><div class="card prose searchable" id="overview"></div></section>
    <section class="panel" data-panel="notes"><div class="card prose searchable" id="notes"></div></section>
    <section class="panel" data-panel="concepts"><div class="concept-grid" id="concepts"></div></section>
    <section class="panel" data-panel="glossary"><div class="glossary-grid" id="glossary"></div></section>
    <section class="panel" data-panel="quiz"><div id="quiz"></div></section>
    <section class="panel" data-panel="cards"><div id="cards"></div></section>
    <section class="panel" data-panel="exercises"><div class="exercise-grid" id="exercises"></div></section>
  </main>
  <footer class="footer">Generated __GENERATED_DATE__ by <strong>Skill-Anything v0.4</strong> · works fully offline</footer>
  <script id="pack-data" type="application/json">__PACK_JSON__</script>
  <script>
  (()=>{'use strict';
    const p=JSON.parse(document.getElementById('pack-data').textContent), $=s=>document.querySelector(s);
    const store={get:(k,d)=>{try{return localStorage.getItem(k)??d}catch{return d}},set:(k,v)=>{try{localStorage.setItem(k,v)}catch{}}};
    const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const inline=s=>esc(s).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');
    function md(src){let out='',list=false;for(const raw of String(src||'').split('\n')){const line=raw.trimEnd();if(/^#{1,4} /.test(line)){if(list){out+='</ul>';list=false}const n=line.match(/^#+/)[0].length;out+=`<h${n}>${inline(line.slice(n+1))}</h${n}>`}else if(/^[-*] /.test(line)){if(!list){out+='<ul>';list=true}out+=`<li>${inline(line.slice(2))}</li>`}else if(!line.trim()){if(list){out+='</ul>';list=false}}else{if(list){out+='</ul>';list=false}out+=`<p>${inline(line)}</p>`}}return out+(list?'</ul>':'')}
    document.title=p.title+' · Skill-Anything';$('#title').textContent=p.title;$('#summary').textContent=p.summary||'A portable interactive study pack.';
    const counts=[['Concepts',(p.key_concepts||[]).length],['Questions',(p.quiz_questions||[]).length],['Flashcards',(p.flashcards||[]).length],['Exercises',(p.practice_exercises||[]).length]];
    $('#stats').innerHTML=counts.map(([k,v])=>`<div class="stat"><strong>${v}</strong><span>${k}</span></div>`).join('');
    $('#meta').innerHTML=[p.source_type,p.source_ref].filter(Boolean).map(x=>`<span class="pill">${esc(x)}</span>`).join('');
    const tabs=[['overview','Overview'],['notes','Notes'],['concepts','Concepts'],['glossary','Glossary'],['quiz','Quiz'],['cards','Flashcards'],['exercises','Exercises']];
    $('#tabs').innerHTML=tabs.map((t,i)=>`<button class="tab ${i?'':'active'}" data-tab="${t[0]}">${t[1]}</button>`).join('');
    const outline=(p.timeline||[]).length?'<h2>Outline</h2><table><thead><tr><th>Position</th><th>Topic</th><th>Summary</th></tr></thead><tbody>'+p.timeline.map(x=>`<tr><td>${esc(x.position)}</td><td>${esc(x.title)}</td><td>${esc(x.summary)}</td></tr>`).join('')+'</tbody></table>':'';
    const pathLabels={prerequisites:'Prerequisites',next_steps:'Next Steps',resources:'Resources'},learning=Object.entries(p.learning_path||{}).filter(([,v])=>v&&v.length).map(([k,v])=>`<h3>${esc(pathLabels[k]||k)}</h3><ul>${v.map(x=>`<li>${inline(x)}</li>`).join('')}</ul>`).join('');
    $('#overview').innerHTML=`<h2>Overview</h2>${md(p.summary)}${outline}${p.cheat_sheet?'<h2>Cheat Sheet</h2>'+md(p.cheat_sheet):''}${(p.takeaways||[]).length?'<h2>Takeaways</h2><ul>'+p.takeaways.map(x=>`<li>${inline(x)}</li>`).join('')+'</ul>':''}${learning?'<h2>Learning Path</h2>'+learning:''}`;
    $('#notes').innerHTML=`<h2>Detailed Notes</h2>${md(p.detailed_notes)||'<p class="muted">No detailed notes in this pack.</p>'}`;
    const empty=t=>`<div class="card empty">No ${t} in this pack.</div>`;
    $('#concepts').innerHTML=(p.key_concepts||[]).map((x,i)=>`<article class="card concept searchable"><span class="muted">${String(i+1).padStart(2,'0')}</span><p>${inline(x)}</p></article>`).join('')||empty('concepts');
    $('#glossary').innerHTML=(p.glossary||[]).map(g=>`<article class="card searchable"><h3>${esc(g.term)}</h3><p>${inline(g.definition)}</p>${(g.related_terms||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</article>`).join('')||empty('glossary entries');
    $('#exercises').innerHTML=(p.practice_exercises||[]).map((e,i)=>`<article class="card searchable"><div class="muted">Exercise ${i+1} · ${esc(e.difficulty||'')}</div><h3>${esc(e.title)}</h3>${md(e.description)}${(e.hints||[]).length?'<details><summary>Hints</summary><ul>'+e.hints.map(x=>`<li>${inline(x)}</li>`).join('')+'</ul></details>':''}${e.solution?`<details><summary>Solution</summary>${md(e.solution)}</details>`:''}</article>`).join('')||empty('exercises');
    let qi=0,known=Number(store.get('sa:'+p.title+':quiz','0'));function quiz(){const a=p.quiz_questions||[];if(!a.length){$('#quiz').innerHTML=empty('quiz questions');return}qi=(qi+a.length)%a.length;const q=a[qi],pct=Math.round(known/a.length*100);$('#quiz').innerHTML=`<div class="quiz-card card"><div class="quiz-head"><span>Question ${qi+1} / ${a.length}</span><span>${esc(q.difficulty)} · ${esc(q.type)}</span></div><div class="progress"><i style="width:${pct}%"></i></div><h2>${esc(q.question)}</h2><div class="options">${(q.options||[]).map(o=>`<div class="option">${esc(o)}</div>`).join('')}</div><div class="answer" id="answer"><strong>${esc(q.answer)}</strong><p>${esc(q.explanation||'')}</p></div><div class="controls"><button class="action primary" id="reveal">Reveal answer</button><button class="action" id="again">Review again</button><button class="action" id="know">I knew this</button><button class="action" id="qnext">Next →</button></div></div>`;$('#reveal').onclick=()=>$('#answer').classList.add('show');$('#again').onclick=()=>{$('#answer').classList.add('show');known=Math.max(0,known-1);store.set('sa:'+p.title+':quiz',known)};$('#know').onclick=()=>{known=Math.min(a.length,known+1);store.set('sa:'+p.title+':quiz',known);qi++;quiz()};$('#qnext').onclick=()=>{qi++;quiz()}}quiz();
    let ci=0,savedCards=[];try{savedCards=JSON.parse(store.get('sa:'+p.title+':cards','[]'))}catch{}const mastered=new Set(savedCards);function cards(){const a=p.flashcards||[];if(!a.length){$('#cards').innerHTML=empty('flashcards');return}ci=(ci+a.length)%a.length;const c=a[ci];$('#cards').innerHTML=`<div class="flash-wrap"><div class="quiz-head"><span>Card ${ci+1} / ${a.length}</span><span>${mastered.size} mastered</span></div><div class="progress"><i style="width:${Math.round(mastered.size/a.length*100)}%"></i></div><div class="flashcard" id="flash"><div class="flash-inner"><div class="face front">${inline(c.front)}</div><div class="face back">${inline(c.back)}</div></div></div><div class="controls"><button class="action" id="prev">← Previous</button><button class="action primary" id="flip">Flip card</button><button class="action" id="master">${mastered.has(ci)?'✓ Mastered':'Mark mastered'}</button><button class="action" id="next">Next →</button></div><div>${(c.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div></div>`;const flip=()=>$('#flash').classList.toggle('flipped');$('#flash').onclick=flip;$('#flip').onclick=flip;$('#prev').onclick=()=>{ci--;cards()};$('#next').onclick=()=>{ci++;cards()};$('#master').onclick=()=>{mastered.has(ci)?mastered.delete(ci):mastered.add(ci);store.set('sa:'+p.title+':cards',JSON.stringify([...mastered]));cards()}}cards();
    document.addEventListener('click',e=>{const b=e.target.closest('[data-tab]');if(!b)return;document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(`[data-panel="${b.dataset.tab}"]`).classList.add('active')});
    $('#search').addEventListener('input',e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('.searchable').forEach(x=>x.style.display=x.textContent.toLowerCase().includes(q)?'':'none')});
    const saved=store.get('sa-theme','');if(saved)document.documentElement.dataset.theme=saved;$('#theme').onclick=()=>{const v=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=v;store.set('sa-theme',v)};
    $('#download').onclick=()=>{const b=new Blob([JSON.stringify(p,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=(p.title||'study-pack').toLowerCase().replace(/[^a-z0-9]+/g,'-')+'.json';a.click();URL.revokeObjectURL(a.href)};
  })();
  </script>
</body>
</html>'''
