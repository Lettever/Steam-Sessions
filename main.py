import json
import os
import sqlite3
import urllib.parse
import urllib.request


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
    data = (game["appid"], diff)
    cur.execute(
        "INSERT INTO Sessions (appid, playtime, date) VALUES (?, ?, DATE('now', '-1 day'))",
        data,
    )
    con.commit()
    return diff


def updateTotalPlaytime(game, diff):
    print(f"Updating the game {game['name']} with {diff} minutes")
    old_total = cur.execute(
        "SELECT total_playtime from Games where appid = ?", (game["appid"],)
    ).fetchone()[0]
    new_total = old_total + diff
    appid = game["appid"]
    cur.execute(
        """
        UPDATE Games
        SET total_playtime = ?
        WHERE appid = ?""",
        (new_total, appid),
    )
    con.commit()


# 491m = 8h, 11m
# 14,7h = 882m = 14h, 42m
# 882m - 491m = 391m = 6h, 31m


def printDailySummary():
    cur.execute("""
            SELECT g.name, s.playtime
            FROM Sessions s
            JOIN Games g ON s.appid = g.appid
            WHERE s.date = DATE('now', '-1 day')""")

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

"""
# getOwnedGames will only be used once to populate the db
getOwnedGames example
{
    "appid":367520,
    "name":"Hollow Knight",
    "playtime_forever":1525,
    "img_icon_url":"f6ab055c2366237200b1a31cccbd6cf81e436d72",
    "has_community_visible_stats":true,
    "playtime_windows_forever":996,
    "playtime_mac_forever":0,
    "playtime_linux_forever":528,
    "playtime_deck_forever":0,
    "rtime_last_played":1767729208,
    "playtime_disconnected":17
}

getRecentGames example
{
    "appid":1030300,
    "name":"Hollow Knight: Silksong",
    "playtime_2weeks":627,
    "playtime_forever":5410,
    "img_icon_url":"b4a999c1302e3ac123c041fd41bb8a34528c6ab5",
    "playtime_windows_forever":4035,
    "playtime_mac_forever":0,
    "playtime_linux_forever":1375,
    "playtime_deck_forever":0
}
"""
