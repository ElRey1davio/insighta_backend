import sqlite3
import uuid6
import json
from datetime import datetime, timezone 

def init_db():
    conn = sqlite3.connect("profiles.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE,
            gender TEXT,
            gender_probability REAL,
            age INTEGER,
            age_group TEXT,
            country_id TEXT,
            country_name TEXT,
            country_probability REAL,
            created_at TEXT
        )
    ''')
    
    c.execute('''
     CREATE TABLE IF NOT EXISTS users(
         id TEXT PRIMARY KEY,
         github_id TEXT UNIQUE,
         username TEXT,
         email TEXT,
         avatar_url TEXT,
         role TEXT DEFAULT 'analyst',
         is_active INTEGER DEFAULT 1,
         last_login_at TEXT,
         created_at TEXT
         
     )
     ''')
    
    c.execute('''
              CREATE TABLE IF NOT EXISTS refresh_tokens(
                  id TEXT PRIMARY KEY,
                  user_id TEXT,
                  token TEXT UNIQUE,
                  expires_at TEXT,
                  created_at TEXT
              )
              ''')
    conn.commit()
    conn.close()

init_db()


def seed_db():
    with open("seed_profiles.json","r")as file:
        data = json.load(file)
    conn = sqlite3.connect("profiles.db")
    c = conn.cursor()
    for profile in data["profiles"]:
        individual_profile_id = str(uuid6.uuid7())
        profile_created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        c.execute('''
    INSERT OR IGNORE INTO profiles (id, name, gender, gender_probability, age, age_group, country_id, country_name, country_probability, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (individual_profile_id, profile["name"].lower(), profile["gender"], profile["gender_probability"], profile["age"], profile["age_group"], profile["country_id"], profile["country_name"], profile["country_probability"], profile_created_at))
    
    
   
   # Seed test users (fixed UUIDs so tokens survive restarts)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    c.execute("INSERT OR IGNORE INTO users (id, github_id, username, email, avatar_url, role, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("019ddd00-0000-7000-8000-000000000001", "000001", "admin_test", "admin@test.com", "", "admin", 1, now))
    c.execute("INSERT OR IGNORE INTO users (id, github_id, username, email, avatar_url, role, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("019ddd00-0000-7000-8000-000000000002", "000002", "analyst_test", "analyst@test.com", "", "analyst", 1, now))
   
    conn.commit()
    conn.close() 
seed_db()    


