"""Check the lessons of a course before they go on the site.

A lesson FAILS when its structure is broken (a section missing or out of order,
not three points in the summary, no practice time, no self-check questions),
when it is far too short or too long, or when it cites a page that is not on
disk in <workspace>/raw/. A citation to a page the course never read is how
invented sources get in, so it is a hard fail.

It WARNS about writing that reads like a clumsy translation: English-style
quotes and hyphens in place of dashes in Russian and Ukrainian text, Title Case
headings, known calques, "ты" and "вы" mixed in one lesson. Warnings are not
proof of a mistake; fix each one or be ready to say why it stays.

Usage: python3 check_lessons.py <workspace> [lessons/NN-handle.md ...]   (default: all)
       --strict  turns warnings into failures
Exit 1 if any lesson fails.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_lib as cl  # noqa: E402

WORDS_MIN, WORDS_MAX = 450, 1200       # whole lesson without links: about 3 to 7 minutes of reading
BODY_MIN = 180
TRY_MAX_MIN = 30

DEMAND = {
    "ru": r"вы должны|ты должн[аы]?|вам следует|тебе следует|вы обязаны|не забудьте|не забудь",
    "uk": r"ви повинні|ти повин(ен|на)|вам слід|тобі слід|ви зобов'язані|не забудьте|не забудь",
    "en": r"you need to|you must|you should|make sure|you have to|don't forget",
}

# Calques and filler that make Russian read like a machine translation. Each entry:
# pattern -> what to write instead. Kept short on purpose: only phrases that are
# almost always wrong in a Russian course text.
CALQUES = {
    "ru": {
        r"\bделает разницу|\bсделать разницу|\bделают разницу": "«меняет дело», «влияет на результат»",
        r"\bна (ежедневной|регулярной|постоянной) основе": "«каждый день», «регулярно», «постоянно»",
        r"\bдавайте (погрузимся|нырнём)|\bпогрузимся в": "просто начните с сути",
        r"\bв этом уроке мы (рассмотрим|поговорим|разберём|узнаем)": "сразу к делу, без анонса",
        r"\bзвучит знакомо\?": "«знакомо?», «бывало такое?»",
        r"\bэто большое дело": "«это важно», «это серьёзно»",
        r"\bв терминах\b": "«с точки зрения», «если говорить о»",
        r"\bадресовать (проблему|вопрос)": "«решить проблему», «заняться вопросом»",
        r"\bчит-?код|\bгеймчейнджер|\bлайфхак": "обычные слова: «приём», «способ», «хитрость»",
        r"\bоке[йи]\b|\bокей\b": "«хорошо», «ладно» или ничего",
        r"\bсупер ?(важн|полезн|прост)": "«очень», «особенно»",
        r"\bв конце дня\b": "если в значении «в итоге»: «в итоге», «в конечном счёте»",
        r"\bхорошая новость в том, что": "«к счастью», «хорошо, что»",
        r"\bиграет (ключевую|важную|решающую) роль": "скажите прямо, что именно оно меняет",
        r"\bявляется\b": "почти всегда лишнее: «X — это Y» или просто «X — Y»",
        r"\bосуществлять|\bосуществить": "назовите действие прямо",
        r"\bданн(ый|ая|ое|ые|ого|ой|ом|ых) (урок|метод|подход|способ|вопрос)": "«этот», «такой»",
        r"\bв рамках\b": "часто лишнее: «на уроке», «за неделю»",
        r"\bпо-настоящему важн": "«важно» (усилитель ослабляет)",
    },
    "uk": {
        r"\bробить різницю": "«змінює справу», «впливає на результат»",
        r"\bна (щоденній|регулярній|постійній) основі": "«щодня», «регулярно», «постійно»",
        r"\bдавайте зануримося|\bзануримося в": "просто почніть із суті",
        r"\bу цьому уроці ми (розглянемо|поговоримо|розберемо)": "одразу до справи",
        r"\bзвучить знайомо\?": "«знайомо?», «бувало таке?»",
        r"\bявляється\b|\bє ключовим": "«X — це Y»",
        r"\bлайфхак|\bчит-?код": "«прийом», «спосіб»",
    },
}


def lang_of(course):
    return course.get("language", "ru")


def prose(text):
    """Text a reader sees as prose: no code, no urls, no markdown link targets."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"^\?\?\? ", "", text, flags=re.M)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return cl.URL.sub(" ", text)


def style_warnings(text, lang, headings):
    found = []
    body = prose(text)
    if lang in ("ru", "uk"):
        if re.search(r"(^|[\s(])\"[^\"\n]+\"", body):
            found.append("прямые кавычки \"…\": в русском и украинском тексте «ёлочки», внутри цитаты „лапки“")
        if re.search(r"\S - \S", body):
            found.append("дефис с пробелами « - » вместо тире: пишите « — »")
        for h in headings:
            words = [w for w in re.findall(r"[A-Za-zА-Яа-яЁёЇїІіЄєҐґ']+", h)]
            if len(words) >= 3 and sum(w[0].isupper() for w in words[1:]) >= 2:
                found.append(f"заголовок «{h}» с Заглавными Словами: с большой буквы только первое слово и имена")
        for pattern, fix in CALQUES.get(lang, {}).items():
            m = re.search(pattern, body, re.I)
            if m:
                found.append(f"«{m.group(0)}» звучит как калька или канцелярит → {fix}")
        tu = len(re.findall(r"\b(ты|тебе|тебя|тобой|твой|твоя|твоё|твои|ти|тобі)\b", body, re.I))
        vy = len(re.findall(r"\b(вы|вам|вас|вами|ваш|ваша|ваше|ваши|ви)\b", body, re.I))
        if tu and vy:
            found.append(f"смешаны «ты» ({tu}) и «вы» ({vy}): выберите одно обращение на весь курс")
        if re.search(r"[^.!?…\n«(]\s+Вы\b|[^.!?…\n«(]\s+Вам\b|[^.!?…\n«(]\s+Ваш", body):
            found.append("«Вы» с большой буквы посреди фразы: в курсе для многих читателей пишут «вы»")
        if re.search(r"[A-Za-z]{3,}[А-Яа-яЁё]|[А-Яа-яЁё][A-Za-z]{3,}", body):
            found.append("латиница и кириллица слиплись в одном слове (опечатка или смешанная раскладка)")
    if re.search(r"!{2,}|\?{2,}", body):
        found.append("двойные !! или ??: в учебном тексте хватает одного знака")
    return found


def check_lesson(lesson, course, lab, known):
    lang = lang_of(course)
    errors, warnings = [], []
    secs = lesson["sections"]
    names = lab["sections"]

    if not lesson["title"]:
        errors.append("нет title в шапке урока (--- title: … ---)")
    if lesson["preamble"]:
        warnings.append("текст до первого раздела ## не попадёт на сайт")
    missing = [names[s] for s in cl.SECTIONS if s not in secs]
    if missing:
        errors.append("нет разделов: " + ", ".join(f"## {m}" for m in missing))
    present = [s for s in lesson["order"] if s in cl.SECTIONS]
    if present != [s for s in cl.SECTIONS if s in present]:
        errors.append("разделы не по порядку: " + " → ".join(names[s] for s in cl.SECTIONS))
    if lesson["unknown"]:
        warnings.append("лишние разделы ## (на сайте станут обычными подзаголовками): " + ", ".join(lesson["unknown"]))

    bullets = [l for l in secs.get("summary", "").splitlines() if re.match(r"^[-*] ", l)]
    if "summary" in secs and len(bullets) != 3:
        errors.append(f"в «{names['summary']}» {len(bullets)} пунктов, нужно ровно 3")

    if "try" in secs:
        parts = lesson["try_parts"]
        minutes = [p for p in parts if re.search(r"\d", p)]
        if not minutes:
            errors.append(f"в заголовке «{names['try']}» нет времени: ## {names['try']} · {lab['energy'][0]} · 10 минут")
        else:
            n = int(re.search(r"\d+", minutes[0]).group(0))
            if n > TRY_MAX_MIN:
                warnings.append(f"практика на {n} минут: в мини-курсе лучше от 2 до {TRY_MAX_MIN}")
        if not any(p in lab["energy"] for p in parts):
            warnings.append(f"в заголовке «{names['try']}» нет типа практики: " + ", ".join(lab["energy"]))

    rule = re.sub(r"\s+", " ", secs.get("rule", "")).strip()
    if "rule" in secs and (not rule or len(re.findall(r"[.!?…](\s|$)", rule)) > 2 or cl.words(rule) > 40):
        errors.append(f"«{names['rule']}» должно быть одним-двумя предложениями (до 40 слов)")

    questions = re.findall(r"^\?\?\? ", secs.get("quiz", ""), re.M)
    if "quiz" in secs and not 2 <= len(questions) <= 4:
        errors.append(f"в «{names['quiz']}» {len(questions)} вопросов (строки «??? вопрос»), нужно от 2 до 4")

    further = cl.cited_urls(secs.get("further", ""))
    if "further" in secs and not 1 <= len(further) <= 4:
        errors.append(f"в «{names['further']}» {len(further)} ссылок, нужно от 1 до 4")

    total = sum(cl.words(v) for k, v in secs.items() if k != "further")
    if not WORDS_MIN <= total <= WORDS_MAX:
        errors.append(f"{total} слов, нужно от {WORDS_MIN} до {WORDS_MAX} (3–7 минут чтения)")
    if "body" in secs and cl.words(secs["body"]) < BODY_MIN:
        errors.append(f"«{names['body']}»: {cl.words(secs['body'])} слов, нужно хотя бы {BODY_MIN}")

    all_text = "\n".join(secs.values())
    cited = cl.cited_urls(all_text)
    if not cited:
        errors.append("урок не ссылается ни на один источник")
    for u in dict.fromkeys(cited):
        if cl.same_page(u) not in known:
            errors.append(f"ссылка на страницу, которой нет в raw/: {u}")

    if lang in DEMAND:
        m = re.search(rf"\b({DEMAND[lang]})\b", prose(all_text), re.I)
        if m:
            warnings.append(f"приказ «{m.group(0)}»: курс предлагает, а не требует; перефразируйте")
    headings = [lesson["title"]] + re.findall(r"^#{2,4} +(.+)$", all_text, re.M)
    warnings += style_warnings(lesson["title"] + "\n" + all_text, lang, headings)
    return errors, warnings, total


def check_plan(ws, course, known):
    problems = []
    plan = ws / "plan.md"
    if plan.exists():
        for u in sorted(set(cl.cited_urls(plan.read_text(encoding="utf-8")))):
            if cl.same_page(u) not in known:
                problems.append(f"plan.md ссылается на страницу, которой нет в raw/: {u}")
    planned = {(l.get("n"), l.get("handle")) for l in course["lessons"]}
    for f in cl.lesson_files(ws):
        if planned and (int(f.stem[:2]), f.stem[3:]) not in planned:
            problems.append(f"{f.name}: нет в course.json → lessons (номер и handle должны совпадать)")
    arcs = len(course["arcs"])
    for l in course["lessons"]:
        if arcs and not 1 <= int(l.get("arc", 1)) <= arcs:
            problems.append(f"урок {l.get('n')}: arc {l.get('arc')} вне списка arcs")
    return problems


def main(argv):
    strict = "--strict" in argv
    args = [a for a in argv if a != "--strict"]
    if not args:
        sys.exit(__doc__)
    sys.stdout.reconfigure(errors="replace")
    ws = Path(args[0]).expanduser().resolve()
    course = cl.load_course(ws)
    lab = cl.labels(course)
    known = {cl.same_page(u) for u in cl.raw_pages(ws)}
    files = [Path(a).resolve() for a in args[1:]] or cl.lesson_files(ws)
    failed = 0
    plan_problems = check_plan(ws, course, known)
    for p in plan_problems:
        print(f"FAIL {p}")
    failed += bool(plan_problems)
    if not files:
        print("уроков пока нет (lessons/NN-handle.md)")
    for f in files:
        if not f.exists():
            print(f"FAIL {f.name}: файла нет")
            failed += 1
            continue
        errors, warnings, total = check_lesson(cl.parse_lesson(f, lab), course, lab, known)
        bad = errors or (strict and warnings)
        status = "FAIL" if bad else ("WARN" if warnings else "ok  ")
        print(f"{status} {f.name} ({total} слов)")
        for e in errors:
            print(f"     ошибка: {e}")
        for w in warnings:
            print(f"     стиль:  {w}")
        failed += bool(bad)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
