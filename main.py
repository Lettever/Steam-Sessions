import json
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def load_env():
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip().strip("\"'")


load_env()

STEAM_API_KEY = os.environ["STEAM_API_KEY"]
STEAM_ID = 76561199007976324
con = sqlite3.connect("sessions.db")
cur = con.cursor()
cur.execute("PRAGMA foreign_keys = ON")


cur.execute("""
    CREATE TABLE IF NOT EXISTS Games (
        appid INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        starting_playtime INTEGER DEFAULT 0,
        total_playtime INTEGER DEFAULT 0
    )""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS Sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appid INTEGER NOT NULL,
        playtime INTEGER NOT NULL,
        date DATE NOT NULL,
        FOREIGN KEY (appid) REFERENCES Games(appid)
    )""")


def getOwnedGames():
    base_url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = [
        ("key", STEAM_API_KEY),
        ("steamid", STEAM_ID),
        ("include_appinfo", True),
        ("include_played_free_games", True),
        ("skip_unvetted_apps", False),
    ]
    url = base_url + "?" + urllib.parse.urlencode(params)
    res = urllib.request.urlopen(url)
    return json.loads(res.read())

    # * Unused but could be nice to have
    # input_json = {
    #    "steamid": STEAM_ID,
    #    "include_appinfo": True,
    #    "include_played_free_games": True,
    #    "appids_filter": [440, 367520, 1030300],
    # }
    #
    # params = {
    #    "key": STEAM_API_KEY,
    #    "format": "json",
    #    "input_json": json.dumps(input_json),
    # }


def getRecentGames():
    base_url = "https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1"
    params = [
        ("key", STEAM_API_KEY),
        ("steamid", STEAM_ID),
    ]
    url = base_url + "?" + urllib.parse.urlencode(params)
    res = urllib.request.urlopen(url)
    return json.loads(res.read())


def needsPopulating():
    print("Checking if database is empty")
    cur.execute("SELECT COUNT(*) FROM Games")
    count = cur.fetchone()[0]
    return count == 0


def makeGameRow(game):
    return (
        game["appid"],
        game["name"],
        game["playtime_forever"],
        game["playtime_forever"],
    )


def populateDatabase():
    """Meant to be used once to populate the database"""
    print("Populating the database")
    data = getOwnedGames()
    games = [makeGameRow(game) for game in data["response"]["games"]]
    cur.executemany(
        "INSERT INTO Games (appid, name, starting_playtime, total_playtime) VALUES (?, ?, ?, ?)",
        games,
    )
    con.commit()


# Demos do not count as 'owned' but they still appear in the recent games api (bruh)
def gameExists(game):
    print(f"Checking if {game['name']} exists")
    appid = game["appid"]
    cur.execute("SELECT COUNT(*) FROM Games WHERE appid = ?", (appid,))
    count = cur.fetchone()[0]
    return count > 0


# Should only happen for newly bought games and demos
def addNewGame(game):
    print(f"Adding {game['name']} to the database")
    g = (
        game["appid"],
        game["name"],
        0,
        0,
    )
    cur.execute(
        "INSERT INTO Games (appid, name, starting_playtime, total_playtime) VALUES (?, ?, ?, ?)",
        g,
    )
    con.commit()


def hasNewSession(game):
    total_playtime = cur.execute(
        "SELECT total_playtime from Games where appid = ?", (game["appid"],)
    ).fetchone()[0]
    return total_playtime < game["playtime_forever"]


def addSession(game):
    print(f"Adding session for {game['name']}")
    total_playtime = cur.execute(
        "SELECT total_playtime from Games where appid = ?", (game["appid"],)
    ).fetchone()[0]
    diff = game["playtime_forever"] - total_playtime
    cur.execute(
        "INSERT INTO Sessions (appid, playtime, date) VALUES (?, ?, ?)",
        (game["appid"], diff, yesterday),
    )
    con.commit()
    return diff


def updateTotalPlaytime(game, diff):
    print(f"Updating the game {game['name']} with {diff} minutes")
    cur.execute(
        "UPDATE Games SET total_playtime = total_playtime + ? WHERE appid = ?",
        (diff, game["appid"]),
    )
    con.commit()


def printDailySummary():
    cur.execute(
        """
            SELECT g.name, s.playtime
            FROM Sessions s
            JOIN Games g ON s.appid = g.appid
            WHERE s.date = ?""",
        (yesterday,),
    )

    sessions = cur.fetchall()
    if sessions:
        print("\nToday's Sessions")
        total = 0
        for name, playtime in sessions:
            print(f"  {name}: +{playtime} minutes")
            total += playtime
        print(f"  TOTAL: {total} minutes")
    else:
        print("No sessions recorded today")


if __name__ == "__main__":
    if needsPopulating():
        populateDatabase()
    else:
        for game in getRecentGames()["response"]["games"]:
            if not gameExists(game):
                addNewGame(game)
            if hasNewSession(game):
                diff_time = addSession(game)
                updateTotalPlaytime(game, diff_time)
    printDailySummary()
