import psycopg2
import os
import datetime
import json
from dotenv import load_dotenv
load_dotenv()

class DatabaseManager:
    """
    A production-ready class to manage all database connections and queries
    for a multi-server Discord bot. It uses a PostgreSQL database for scalability.
    """

    def __init__(self):
        self._create_tables()

    def _get_connection(self):
        """
        Establishes and returns a database connection using the DATABASE_URL
        from your .env file.
        """
        try:
            # Retrieve the connection URL from the environment variable
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise ValueError("DATABASE_URL environment variable is not set.")
                
            return psycopg2.connect(database_url)
        except Exception as e:
            print(f"Error connecting to database: {e}")
            return None

    def _create_tables(self):
        """
        Creates the necessary tables if they do not already exist.
        - global_winners: Stores winners for all games and servers.
        - user_stats: Stores game-specific stats for each user on each server.
        - server_settings: Stores settings for each guild (e.g., game master role).
        """
        try:
            conn = self._get_connection()
            if conn is None:
                print("Failed to create tables due to connection error.")
                return

            with conn.cursor() as cursor:
                # Table for winners (e.g., Trivia, Scramble, etc.)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS global_winners (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        username TEXT,
                        game_name TEXT NOT NULL,
                        host_id TEXT,
                        host_name TEXT,
                        timestamp TIMESTAMPTZ NOT NULL,
                        guild_id TEXT NOT NULL
                    );
                ''')
                
                # Table for user stats (e.g., number of wins, streaks, etc.)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_stats (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        guild_id TEXT NOT NULL,
                        game_name TEXT NOT NULL,
                        wins INT DEFAULT 0,
                        losses INT DEFAULT 0,
                        last_played TIMESTAMPTZ,
                        UNIQUE(user_id, guild_id, game_name)
                    );
                ''')
                
                # Table for server settings
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS server_settings (
                        guild_id TEXT PRIMARY KEY,
                        allowed_roles TEXT NOT NULL
                    );
                ''')
                
            conn.commit()
            conn.close()
            print("Database tables are ready!")
        except Exception as e:
            print(f"Error creating tables: {e}")

    def add_winner(self, user_id, username, game_name, host_id, host_name, guild_id):
        """Adds a single winner to the global_winners table."""
        try:
            conn = self._get_connection()
            if conn is None: return False

            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO global_winners 
                    (user_id, username, game_name, host_id, host_name, timestamp, guild_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                ''', (str(user_id), username, game_name, str(host_id), host_name, datetime.datetime.now(), str(guild_id)))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Database error adding winner: {e}")
            return False

    def get_recent_winners_for_guild(self, guild_id, game_name=None, limit=10):
        """
        Fetches the most recent winners for a specific guild and an optional game.
        Returns a list of dictionaries.
        """
        try:
            conn = self._get_connection()
            if conn is None: return []

            sql_query = """
                SELECT user_id, username, game_name, host_id, host_name, timestamp
                FROM global_winners
                WHERE guild_id = %s
            """
            params = [str(guild_id)]
            
            if game_name:
                sql_query += " AND game_name = %s"
                params.append(game_name)

            sql_query += " ORDER BY timestamp DESC LIMIT %s;"
            params.append(limit)
            
            with conn.cursor() as cursor:
                cursor.execute(sql_query, tuple(params))
                rows = cursor.fetchall()
            conn.close()

            winners = []
            for row in rows:
                winners.append({
                    'user_id': row[0],
                    'username': row[1],
                    'game_name': row[2],
                    'host_id': row[3],
                    'host_name': row[4],
                    'timestamp': row[5].strftime("%b %d, %Y %I:%M %p")
                })
            return winners
        except Exception as e:
            print(f"Database error fetching winners: {e}")
            return []

    def clear_leaderboard_for_guild(self, guild_id, game_name=None):
        """Deletes winner records for a specific guild and an optional game."""
        try:
            conn = self._get_connection()
            if conn is None: return False

            sql_query = "DELETE FROM global_winners WHERE guild_id = %s"
            params = [str(guild_id)]
            
            if game_name:
                sql_query += " AND game_name = %s"
                params.append(game_name)
            
            with conn.cursor() as cursor:
                cursor.execute(sql_query, tuple(params))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Database error clearing leaderboard: {e}")
            return False
            
    def update_user_stats(self, user_id, guild_id, game_name, wins=0, losses=0):
        """
        Inserts or updates a user's win/loss stats for a specific game on a specific guild.
        """
        try:
            conn = self._get_connection()
            if conn is None: return False
            
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO user_stats (user_id, guild_id, game_name, wins, losses, last_played)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, guild_id, game_name) DO UPDATE 
                    SET 
                        wins = user_stats.wins + EXCLUDED.wins, 
                        losses = user_stats.losses + EXCLUDED.losses,
                        last_played = EXCLUDED.last_played;
                ''', (str(user_id), str(guild_id), game_name, wins, losses, datetime.datetime.now()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Database error updating stats: {e}")
            return False

    def get_user_stats(self, user_id, guild_id, game_name):
        """Fetches a user's stats for a specific game on a specific guild."""
        try:
            conn = self._get_connection()
            if conn is None: return None

            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT wins, losses, last_played FROM user_stats
                    WHERE user_id = %s AND guild_id = %s AND game_name = %s;
                ''', (str(user_id), str(guild_id), game_name))
                
                result = cursor.fetchone()
            conn.close()

            if result:
                return {
                    'wins': result[0],
                    'losses': result[1],
                    'last_played': result[2].strftime("%b %d, %Y %I:%M %p")
                }
            return None
        except Exception as e:
            print(f"Database error fetching stats: {e}")
            return None

    def update_server_settings(self, guild_id, allowed_roles):
        """
        Inserts or updates server-specific settings.
        """
        try:
            conn = self._get_connection()
            if conn is None: return False
            
            settings_json = json.dumps({'allowed_roles': allowed_roles})

            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO server_settings (guild_id, allowed_roles)
                    VALUES (%s, %s)
                    ON CONFLICT (guild_id) DO UPDATE 
                    SET allowed_roles = EXCLUDED.allowed_roles;
                ''', (str(guild_id), settings_json))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Database error updating server settings: {e}")
            return False
    
    def get_server_settings(self, guild_id):
        """
        Fetches server-specific settings.
        """
        try:
            conn = self._get_connection()
            if conn is None: return None

            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT allowed_roles FROM server_settings
                    WHERE guild_id = %s;
                ''', (str(guild_id),))
                
                result = cursor.fetchone()
            conn.close()

            if result:
                return json.loads(result[0])
            return None
        except Exception as e:
            print(f"Database error fetching server settings: {e}")
            return None
            
if __name__ == '__main__':
    # This block will be executed if you run the file directly
    db_manager = DatabaseManager()
    print("Database manager initialized. Tables are being created/checked.")