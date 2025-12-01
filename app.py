import tkinter as tk
from tkinter import ttk, messagebox
import time
import random
import threading
import requests
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================
# Set this to False to use the REAL API (requires API Key)
USE_SIMULATION_MODE = True 

# API DETAILS (Only needed if USE_SIMULATION_MODE = False)
# Get a free key from: https://www.football-data.org/
API_KEY = "YOUR_API_KEY_HERE" 
API_URL = "https://api.football-data.org/v4/matches"

class Match:
    """Data class to hold match information."""
    def __init__(self, id, home_team, away_team, home_score, away_score, status, minute):
        self.id = id
        self.home_team = home_team
        self.away_team = away_team
        self.home_score = home_score
        self.away_score = away_score
        self.status = status # 'SCHEDULED', 'LIVE', 'PAUSED', 'FINISHED'
        self.minute = minute

class DataService:
    """Base class for data fetching logic."""
    def fetch_matches(self):
        raise NotImplementedError

class RealDataService(DataService):
    """Fetches real data from football-data.org API."""
    def fetch_matches(self):
        headers = {'X-Auth-Token': API_KEY}
        try:
            # Fetching matches for today
            response = requests.get(API_URL, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            matches = []
            for m in data.get('matches', []):
                status = m['status']
                
                # Map API status to our simple status
                display_status = status
                minute = ""
                
                if status == 'IN_PLAY':
                    display_status = 'LIVE'
                    # Calculate rough minute (API doesn't always give exact minute in free tier easily)
                    # This is a simplification
                    minute = "Live" 
                elif status == 'PAUSED':
                    display_status = 'HT'
                elif status == 'FINISHED':
                    display_status = 'FT'
                
                match_obj = Match(
                    id=m['id'],
                    home_team=m['homeTeam']['name'],
                    away_team=m['awayTeam']['name'],
                    home_score=m['score']['fullTime']['home'] if m['score']['fullTime']['home'] is not None else 0,
                    away_score=m['score']['fullTime']['away'] if m['score']['fullTime']['away'] is not None else 0,
                    status=display_status,
                    minute=minute
                )
                matches.append(match_obj)
            return matches
            
        except Exception as e:
            print(f"API Error: {e}")
            return []

class MockDataService(DataService):
    """Generates fake live data for demonstration purposes."""
    def __init__(self):
        self.matches = [
            Match(1, "Arsenal", "Chelsea", 0, 0, "LIVE", 12),
            Match(2, "Real Madrid", "Barcelona", 1, 1, "LIVE", 34),
            Match(3, "Man City", "Liverpool", 2, 0, "HT", 45),
            Match(4, "Bayern Munich", "Dortmund", 0, 0, "SCHEDULED", 0),
            Match(5, "Juventus", "AC Milan", 3, 2, "FINISHED", 90),
        ]
    
    def fetch_matches(self):
        # Simulate live updates
        for match in self.matches:
            if match.status == "LIVE":
                match.minute += 1
                if match.minute > 90:
                    match.status = "FINISHED"
                
                # Random chance to score
                if random.random() < 0.05: # 5% chance updates per refresh
                    if random.choice([True, False]):
                        match.home_score += 1
                    else:
                        match.away_score += 1
            
            elif match.status == "SCHEDULED":
                # Random chance to start
                if random.random() < 0.1:
                    match.status = "LIVE"
                    match.minute = 1
                    
        return self.matches

class LiveScoreApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Live Match Ticker")
        self.root.geometry("600x500")
        self.root.configure(bg="#f0f2f5")

        # Select Data Source
        if USE_SIMULATION_MODE:
            self.service = MockDataService()
            self.status_text = "Source: Simulation Mode"
        else:
            self.service = RealDataService()
            self.status_text = "Source: Real API (football-data.org)"

        # GUI Styles
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Card.TFrame", background="white", relief="flat")
        style.configure("Score.TLabel", font=("Helvetica", 16, "bold"), background="white", foreground="#333")
        style.configure("Team.TLabel", font=("Helvetica", 12), background="white", foreground="#555")
        style.configure("Status.TLabel", font=("Helvetica", 10, "bold"), background="white", foreground="#e74c3c")
        style.configure("Header.TLabel", font=("Helvetica", 18, "bold"), background="#2c3e50", foreground="white")

        self.create_widgets()
        self.refresh_data()

    def create_widgets(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        lbl_title = ttk.Label(header_frame, text="⚽ Live ScoreCenter", style="Header.TLabel", background="#2c3e50")
        lbl_title.pack(pady=15)

        # Status Bar
        self.lbl_status = tk.Label(self.root, text=self.status_text, bg="#f0f2f5", fg="#7f8c8d", font=("Arial", 9))
        self.lbl_status.pack(pady=5)

        # Scrollable Area for Matches
        self.canvas = tk.Canvas(self.root, bg="#f0f2f5", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=10)
        self.scrollbar.pack(side="right", fill="y")

    def refresh_data(self):
        """Fetches data in background thread to keep UI responsive."""
        threading.Thread(target=self._fetch_and_update, daemon=True).start()
        
        # Schedule next refresh in 5 seconds
        self.root.after(5000, self.refresh_data)

    def _fetch_and_update(self):
        matches = self.service.fetch_matches()
        # Schedule UI update on main thread
        self.root.after(0, lambda: self.update_ui(matches))

    def update_ui(self, matches):
        # Clear existing widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        if not matches:
            lbl = tk.Label(self.scrollable_frame, text="No live matches found or API Error.", bg="#f0f2f5")
            lbl.pack(pady=20)
            return

        for match in matches:
            self.create_match_card(match)

    def create_match_card(self, match):
        card = ttk.Frame(self.scrollable_frame, style="Card.TFrame", padding=15)
        card.pack(fill="x", pady=5, padx=5)

        # Layout:  [Time/Status]  [Home Team]  [Score]  [Away Team]
        
        # Status Column
        status_color = "#e74c3c" if match.status == "LIVE" else "#7f8c8d"
        time_text = f"{match.minute}'" if match.status == "LIVE" else match.status
        
        lbl_status = tk.Label(card, text=time_text, font=("Arial", 10, "bold"), fg=status_color, bg="white", width=6)
        lbl_status.pack(side="left", padx=(0, 10))

        # Teams and Score
        # Using a grid inside the card for better alignment
        content_frame = tk.Frame(card, bg="white")
        content_frame.pack(side="left", fill="x", expand=True)

        lbl_home = ttk.Label(content_frame, text=match.home_team, style="Team.TLabel", anchor="e")
        lbl_score = ttk.Label(content_frame, text=f"{match.home_score} - {match.away_score}", style="Score.TLabel", anchor="center")
        lbl_away = ttk.Label(content_frame, text=match.away_team, style="Team.TLabel", anchor="w")

        lbl_home.grid(row=0, column=0, sticky="ew", padx=5)
        lbl_score.grid(row=0, column=1, padx=15)
        lbl_away.grid(row=0, column=2, sticky="ew", padx=5)

        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(2, weight=1)

if __name__ == "__main__":
    root = tk.Tk()
    app = LiveScoreApp(root)
    root.mainloop()