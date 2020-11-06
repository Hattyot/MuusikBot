# MuusikBot
A music bot for discord with a dedicated music menu that display the current song, its progress and songs in the queue.
![Music Menu](https://cdn.discordapp.com/attachments/762328958276075561/774306742494429194/unknown.png)
## Install Guide
##### 1. Download or clone the bot
```
$ git clone https://github.com/Hattyot/MuusikBot.git
$ cd MuusikBot
```
##### 2. install required modules
```
$ pip install -r requirements.txt
```
##### 3. Rename **config_example.py** to **config.py** and add relevant info
##### 4. Install community edition mongodb server. Installation guides: https://docs.mongodb.com/manual/administration/install-community/
##### 5. Run the bot
```
$ python3 bot.py
```
## Running with docker
```
$ docker-compose build
$ docker-compose up -d
```
