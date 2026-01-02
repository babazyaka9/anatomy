import json
import re
import pdfplumber

def is_bold(font_name):
    if not font_name: return False
    name = font_name.lower()
    return "bold" in name or "bld" in name or "black" in name or "heavy" in name

def clean_text(text):
    # Заміна нерозривних пробілів та інших спецсимволів на звичайний пробіл
    text = text.replace('\u00a0', ' ')
    return re.sub(r'\s+', ' ', text).strip()

def split_merged_options(line_data):
    """
    Агресивно розрізає рядок, якщо знаходить всередині літеру варіанту.
    Працює для: "А. Текст В. Текст", "А) Текст В) Текст"
    """
    text = line_data["text"]
    is_bold_flag = line_data["is_bold"]
    
    # Регулярка: шукаємо пробіл (або початок рядка), потім Літеру (А-Е, A-E), потім крапку або дужку.
    # (?<=\s) - lookbehind: перевіряє, чи є пробіл перед літерою (щоб не різати слова типу "DNA.")
    # Але для простоти і надійності просто замінимо " Пробіл+Літера+Крапка" на "\nЛітера+Крапка"
    
    # Патерн: (пробіл) + (Літера А-Е кирилиця/латиниця) + (крапка або дужка)
    # Ми додаємо спец-розділювач |BRK|
    pattern = r'(\s+)([A-EА-Еa-e][\.\)])'
    
    # Замінюємо на: |BRK| + Літера + Дужка
    modified_text = re.sub(pattern, r'|BRK|\2', text)
    
    if '|BRK|' not in modified_text:
        return [line_data]
    
    result_lines = []
    parts = modified_text.split('|BRK|')
    
    for part in parts:
        cleaned = part.strip()
        if cleaned:
            # Якщо ми розрізали рядок, ми дублюємо атрибут жирності.
            # Це не ідеально (бо жирним міг бути тільки варіант А), але краще ніж втратити текст.
            result_lines.append({"text": cleaned, "is_bold": is_bold_flag})
            
    return result_lines

def parse_pdf(filename):
    questions = []
    print(f"Обробляю файл: {filename}")
    
    with pdfplumber.open(filename) as pdf:
        raw_lines = []
        
        for i, page in enumerate(pdf.pages):
            width = page.width
            height = page.height
            
            # Мінімальна обрізка полів
            try:
                cropped = page.crop((0, 10, width, height - 10))
            except:
                cropped = page

            words = cropped.extract_words(keep_blank_chars=True, extra_attrs=["fontname"])
            if not words: continue
            
            # Сортування: строго зверху вниз, потім зліва направо
            words.sort(key=lambda w: (int(w['top']), w['x0']))
            
            line_buffer = []
            if not words: continue
            
            last_top = words[0]['top']
            has_bold = False
            
            for w in words:
                # Чутливість до нового рядка - 4 пікселі
                if abs(w['top'] - last_top) > 4:
                    text_str = " ".join([wb['text'] for wb in line_buffer])
                    if text_str.strip():
                        raw_lines.append({"text": text_str, "is_bold": has_bold})
                    
                    line_buffer = []
                    has_bold = False
                    last_top = w['top']
                
                line_buffer.append(w)
                if is_bold(w['fontname']):
                    has_bold = True
            
            if line_buffer:
                text_str = " ".join([wb['text'] for wb in line_buffer])
                if text_str.strip():
                    raw_lines.append({"text": text_str, "is_bold": has_bold})

    # РОЗРІЗАННЯ ЗЛИПЛИХ РЯДКІВ
    processed_lines = []
    for line in raw_lines:
        processed_lines.extend(split_merged_options(line))

    # ПАРСИНГ ПИТАНЬ
    current_q = None
    
    # Регулярки
    opt_pattern = re.compile(r'^\s*([A-EА-Еa-e])[\.\)]\s*(.*)', re.IGNORECASE)
    q_pattern = re.compile(r'^\s*(\d+)\.\s*(.*)')

    for line_data in processed_lines:
        text = clean_text(line_data["text"])
        is_bold_line = line_data["is_bold"]
        
        if not text: continue
        # Пропуск номерів сторінок (якщо рядок це просто цифри)
        if text.isdigit() and len(text) < 4: continue

        # 1. Це варіант відповіді?
        match_opt = opt_pattern.match(text)
        if match_opt and current_q:
            opt_text = match_opt.group(2).strip()
            # Якщо текст пустий (рядок "А."), беремо зріз
            if not opt_text: opt_text = text[2:].strip() if len(text) > 2 else ""

            current_q["opts"].append(opt_text)
            
            # Логіка визначення правильної відповіді:
            # Якщо рядок жирний, АБО якщо це єдина жирна літера
            if is_bold_line:
                current_q["c"] = len(current_q["opts"]) - 1
            continue

        # 2. Це нове питання?
        match_q = q_pattern.match(text)
        if match_q:
            # Зберігаємо попереднє
            if current_q:
                # Валідація: зберігаємо тільки якщо є варіанти
                if current_q['opts']:
                    if current_q['c'] == -1: current_q['c'] = 0
                    questions.append(current_q)
            
            current_q = {
                "id": int(match_q.group(1)),
                "q": match_q.group(2).strip(),
                "opts": [],
                "c": -1
            }
            continue
        
        # 3. Продовження тексту
        if current_q:
            if current_q["opts"]:
                current_q["opts"][-1] += " " + text
            else:
                current_q["q"] += " " + text

    # Останнє питання
    if current_q and current_q['opts']:
        if current_q['c'] == -1: current_q['c'] = 0
        questions.append(current_q)

    return questions

if __name__ == "__main__":
    try:
        data = parse_pdf('base.pdf')
        print(f"Знайдено {len(data)} питань.")
        with open('questions.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Помилка: {e}")
        with open('questions.json', 'w', encoding='utf-8') as f:
            json.dump([], f)
