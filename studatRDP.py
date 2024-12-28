import pystray
from PIL import Image, ImageDraw
from PyQt5.QtWidgets import (QApplication, QMainWindow, QSystemTrayIcon, QMenu, QAction, 
                             QVBoxLayout, QLineEdit, QListWidget, QWidget, QDialog, QLabel)
import qasync
from PyQt5.QtGui import QIcon
import sys
import requests
from bs4 import BeautifulSoup
import asyncio
import json
from datetime import datetime, timedelta
from functools import lru_cache
import os
import pickle
import sys
import tempfile
import subprocess
from dotenv import load_dotenv  # Added to import dotenv for loading environment variables

class AuthenticatedSession:
    def __init__(self, username: str, password: str, url: str):
        self.auth_url = url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.login()

    def login(self):
        response = self.session.get(self.auth_url)
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form")
        action = form["action"]
        form_url = f"https://idp.chalmers.se{action}"

        data = {
            'UserName': self.username,
            'Password': self.password,
            'AuthMethod': 'FormsAuthentication'
        }

        response = self.session.post(form_url, data=data)
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("span", id="errorText")
        if form:
            error_message = form.text.strip()
            raise Exception(f"Login failed: {error_message}")

        form = soup.find('form')
        if form:
            action_url = form['action']
            data = {input_tag['name']: input_tag['value'] for input_tag in form.find_all('input', type='hidden')}
            response = self.session.post(action_url, data=data)
            if response.status_code != 200:
                raise Exception("Login failed during redirection process")

        print("Login successful")

    def get(self, url: str):
        response = self.session.get(url)
        if response.status_code == 200:
            return response.text
        else:
            raise Exception(f"Failed to fetch URL: {url}")

    def post(self, url: str, data: dict):
        response = self.session.post(url, data=data)
        if response.status_code == 200:
            return response.text
        else:
            raise Exception(f"Failed to post data to URL: {url}")

async def fetch_schedule(id: str, session: AuthenticatedSession):
    url = f"https://cloud.timeedit.net/chalmers/web/b1/ri.json?h=f&sid=3&p=0.m,12.n&objects={id}&ox=0&types=0&fe=0&h2=f&l=en_EN"
    return session.get(url)

async def fetch_all_schedules(mapping: dict, session: AuthenticatedSession):
    tasks = {key: fetch_schedule(value, session) for key, value in mapping.items()}
    responses = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), responses))

def parse_next_lesson(next_lesson):
    if next_lesson is False:
        return (True, None)
    else:
        date_str = next_lesson['date']
        time_str = next_lesson['time']
        dt_str = f"{date_str} {time_str}"
        return (False, datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))

@lru_cache(maxsize=1)
def get_cached_schedule():
    if os.path.exists('schedule_cache.pkl'):
        with open('schedule_cache.pkl', 'rb') as f:
            cache_data = pickle.load(f)
            last_updated, schedule = cache_data
            if datetime.now() - last_updated < timedelta(days=1):
                return schedule
    return None

def cache_schedule(schedule):
    with open('schedule_cache.pkl', 'wb') as f:
        pickle.dump((datetime.now(), schedule), f)

async def get_computers(auth_session: AuthenticatedSession):
    url_to_fetch = "https://vacantcomp.studat.chalmers.se/Sd/GetData"
    datorer = json.loads(auth_session.post(url_to_fetch, {}))

    schedule_cache = get_cached_schedule()
    if not schedule_cache:
        with open('salar.json', 'r') as file:
            salar = json.load(file)
        schedule_cache = await fetch_all_schedules(salar, timeedit_auth_session)
        cache_schedule(schedule_cache)

    datorerMedScheman = []
    for dator in datorer:
        room = dator.get("room")
        #print(schedule_cache["207164.186"])
        if room in schedule_cache:
            datorschema = json.loads(schedule_cache[room])
            #print(datorschema)
            if dator.get("computername") and dator.get("computerActive") and dator.get("usageStatus"):
                next_lesson = {
                    "date": datorschema["reservations"][0]["startdate"],
                    "time": datorschema["reservations"][0]["starttime"]
                } if datorschema["reservations"] else False
                datorerMedScheman.append({
                    "nextLesson": next_lesson,
                    "computerName": dator.get("computername"),
                    "active": dator.get("computerActive"),
                    "usageStatus": dator.get("usageStatus")
                })

    filtrerade_datorer = [item for item in datorerMedScheman if item['usageStatus'] == 'free' and item['active'] == 'active']
    sorterade_datorer = sorted(filtrerade_datorer, key=lambda x: parse_next_lesson(x['nextLesson']), reverse=True)

    return sorterade_datorer

async def get_top_10_computers(auth_session: AuthenticatedSession):
    computers = await get_computers(auth_session)
    top_10_computers = computers[:10]
    return top_10_computers


#### TRAY SUFF
def on_click(computer):
    # Function to handle item click, you can add logic here
    print(f"Clicked on: {computer}")
    tet = auth_session.get("https://vacantcomp.studat.chalmers.se/File/DownloadFileRdp?selComp=" + str(computer.get("computerName")))

    rdp_config = tet + f"""
    username:s:{username}
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix='.rdp') as temp_file:
        temp_file.write(rdp_config.encode('utf-8'))
        temp_file_path = temp_file.name

    try:
        # Launch the RDP session using the temporary file
        subprocess.run(['mstsc', temp_file_path])
    finally:
        # Clean up the temporary file
        os.remove(temp_file_path)

class ComputerWindow(QMainWindow):
    def __init__(self, computers):
        super().__init__()
        self.setWindowTitle("All Computers")
        self.setGeometry(100, 100, 600, 400)

        # Create the layout for the window
        layout = QVBoxLayout()

        # Create a search field
        self.search_field = QLineEdit(self)
        self.search_field.setPlaceholderText("Search for a computer...")
        self.search_field.textChanged.connect(self.filter_computers)

        # Create a list widget to show the computers
        self.computer_list = QListWidget(self)
        self.computer_list.itemDoubleClicked.connect(self.on_computer_click)  # Connect click event

        # Store the computers list
        self.computers = computers
        self.filtered_computers = computers  # Initially, all computers are shown

        # Populate the list with all computers
        self.update_computer_list()

        # Add the search field and computer list to the layout
        layout.addWidget(self.search_field)
        layout.addWidget(self.computer_list)

        # Create a container widget and set the layout
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def update_computer_list(self):
        """Update the list widget with filtered computers."""
        self.computer_list.clear()  # Clear the list before updating
        for computer in self.filtered_computers:
            text = f"{computer['computerName']}: {computer['usageStatus']}"
            if computer.get("nextLesson"):
                text += f" until {computer['nextLesson']['date']} {computer['nextLesson']['time']}"
            self.computer_list.addItem(text)

    def on_computer_click(self, item):
        """Handle the event when a computer is clicked."""
        # Extract the computer name from the clicked item
        clicked_computer = next(comp for comp in self.computers if comp['computerName'] in item.text())

        # Now trigger the RDP connection
        on_click(clicked_computer)

    def filter_computers(self):
        """Filter the computer list based on the search query."""
        query = self.search_field.text().lower()
        self.filtered_computers = [comp for comp in self.computers if query in comp['computerName'].lower()]
        self.update_computer_list()

async def create_menu(computers):
    menu = QMenu()
    for computer in computers:
        text = f"{computer['usageStatus']}"
        if(computer.get("nextLesson")):
            text = f"{computer['usageStatus']} until {computer['nextLesson']['date']} {computer['nextLesson']['time']}"
        action = QAction(f"{computer['computerName']}: {text}", menu)
        action.setToolTip(f"Name: {computer['computerName']}\nActive: {computer['active']}\nUsage Status: {computer['usageStatus']}")
        action.triggered.connect(lambda checked, comp=computer: on_click(comp))
        menu.addAction(action)
    
    # Add "Show More" action to the tray menu
    show_more_action = QAction("Show More", menu)
    show_more_action.triggered.connect(trigger_show_more_computers)  # Run async function without await
    menu.addAction(show_more_action)

    refresh_action = QAction("Refresh", menu)
    refresh_action.triggered.connect(refresh_menu)
    menu.addAction(refresh_action)
    
    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(QApplication.instance().quit)
    menu.addAction(quit_action)
    return menu

def trigger_show_more_computers():
    """Trigger the show_more_computers coroutine asynchronously."""
    print("Tet")
    asyncio.create_task(show_more_computers())

async def show_more_computers():
    """Function to display the new window with all computers."""
    global tray_icon

    print("tes")
    computers = await get_computers(auth_session)

    # Store the window instance as an attribute of tray_icon to prevent garbage collection
    tray_icon.computer_window = ComputerWindow(computers)
    tray_icon.computer_window.show()


async def refresh_menu():
    global tray_icon
    top_10_computers = await get_top_10_computers(auth_session)
    tray_icon.setContextMenu(create_menu(top_10_computers))

async def create_tray_icon():
    menu = await create_menu(await get_top_10_computers(auth_session))
    tray_icon.setIcon(QIcon(os.path.join('icon.png')))
    tray_icon.setContextMenu(menu)
    tray_icon.show()


async def main():
    global auth_session, timeedit_auth_session, tray_icon, username, password
    # Load the .env file
    load_dotenv()

    username = os.getenv("CID_USERNAME")
    password = os.getenv("CID_PASSWORD") 
    auth_session = AuthenticatedSession(username, password, "https://vacantcomp.studat.chalmers.se/")
    timeedit_auth_session = AuthenticatedSession(username, password, "https://cloud.timeedit.net/chalmers/web/timeedit/sso/saml2")

    top_10_computers = await get_top_10_computers(auth_session)
    print(top_10_computers)
    
    app = QApplication(sys.argv)
    
    # Integrate qasync with the PyQt5 application
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    tray_icon = QSystemTrayIcon()
    await create_tray_icon()

    # Start the event loop
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    asyncio.run(main())