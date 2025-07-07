import time
import json
import schedule
import os
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from facebook import GraphAPI

# === CONFIGURATION ===
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")
DATA_FILE = "scores.json"
URL = "https://www.matchendirect.fr/live-score/"

# === SELENIUM ===
def get_browser():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# === FACEBOOK ===
graph = GraphAPI(access_token=ACCESS_TOKEN)

def publish_to_facebook(message):
    try:
        graph.put_object(parent_object=PAGE_ID, connection_name="feed", message=message)
        print(f"[FB] Posté : {message}")
    except Exception as e:
        print(f"[ERREUR FACEBOOK] {e}")

# === SCORES ===
def load_old_scores():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_scores(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def get_live_scores():
    print("🔎 Scraping des scores...")
    scores = {}
    try:
        driver = get_browser()
        driver.get(URL)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        with open("page_debug.html", "w", encoding="utf-8") as f:
            f.write(soup.prettify())

        driver.quit()

        match_blocks = soup.select("td.lm3")

        for match in match_blocks:
            try:
                eq1 = match.select_one("span.lm3_eq1").text.strip()
                eq2 = match.select_one("span.lm3_eq2").text.strip()
                score1 = match.select_one("span.scored_1").text.strip()
                score2 = match.select_one("span.scored_2").text.strip()

                row = match.find_parent("tr")
                statut_td = row.select_one("td.lm2.lm2_1")
                minute = statut_td.text.strip() if statut_td else ""

                # Normalisation statut
                if minute.lower() in ["mi-temps", "mt"]:
                    statut = "MT"
                elif "ter" in minute.lower() or "terminé" in minute.lower():
                    statut = "TER"
                else:
                    statut = ""

                key = f"{eq1} vs {eq2}"
                score = f"{score1} - {score2}"
                scores[key] = {"score": score, "statut": statut, "minute": minute, "eq1": eq1, "eq2": eq2}

            except Exception as e:
                print("❌ Erreur sur un match:", e)

    except Exception as e:
        print(f"[ERREUR SELENIUM] {e}")

    print("✅ Scores trouvés :", scores)
    return scores

# === VERIF & POST ===
def check_and_post():
    old_scores = load_old_scores()
    new_scores = get_live_scores()

    for match, data in new_scores.items():
        new_score = data["score"]
        new_statut = data["statut"]
        minute = data.get("minute", "")
        eq1 = data.get("eq1", "")
        eq2 = data.get("eq2", "")

        if match not in old_scores:
            # Nouveau match commencé
            if new_score != " - " and "'" in minute:
                msg = f"🟢 Démarré 1ère Mi-Temps : {match} → {new_score} ({minute})"
                publish_to_facebook(msg)
            continue

        old_data = old_scores[match]
        old_score = old_data.get("score")
        old_statut = old_data.get("statut")

        changement_score = new_score != old_score
        changement_statut = new_statut != old_statut and new_statut in ["MT", "TER"]

        if changement_statut:
            if new_statut == "MT":
                msg = f"⏸️ Mi-temps : {match} → {new_score} (MT)"
            elif new_statut == "TER":
                msg = f"🔚 Match terminé : {match} → {new_score} (TER)"
            publish_to_facebook(msg)

        elif changement_score:
            # Détection de l'équipe qui a marqué
            try:
                s1_old, s2_old = map(int, old_score.split(" - "))
                s1_new, s2_new = map(int, new_score.split(" - "))
                if s1_new > s1_old:
                    equipe_but = eq1
                elif s2_new > s2_old:
                    equipe_but = eq2
                else:
                    equipe_but = "⚽ But"
            except:
                equipe_but = "⚽ But"

            msg = f"⚽ Buuuut de {equipe_but} !\n{match} → {new_score} ({minute})"
            publish_to_facebook(msg)

    save_scores(new_scores)

# === RÉSUMÉ GLOBAL ===
def post_all_live_scores():
    scores = load_old_scores()
    message = "📊 Scores en direct :\n\n"
    matchs_en_cours = 0

    for match, data in scores.items():
        score = data["score"]
        statut = data["statut"]
        minute = data.get("minute", "")

        if statut != "TER":
            ligne = f"{match} → {score}"
            if statut:
                ligne += f" ({statut})"
            elif "'" in minute:
                ligne += f" ({minute})"
            message += f"- {ligne}\n"
            matchs_en_cours += 1

    if matchs_en_cours > 0:
        publish_to_facebook(message.strip())
    else:
        print("📭 Aucun match en cours.")

# === LANCEMENT ===
print("🚀 Scraper lancé avec surveillance continue.")
check_and_post()
post_all_live_scores()

schedule.every(60).seconds.do(check_and_post)
schedule.every(30).minutes.do(post_all_live_scores)

while True:
    schedule.run_pending()
    time.sleep(5)
