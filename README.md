# Live translator

* https://github.com/openai/whisper (not used for now.. too slow)
* https://github.com/alphacep/vosk-api

### mac OS config
https://github.com/ExistentialAudio/BlackHole/wiki/Multi-Output-Device
    
right click BlakHole and select "Use This Device For Sound Output"

find the blackhole device : ```python3 translate.py -l```

and pass it to the -d option :

```
python3 translate.py -d 2
# or choose a another language
python3 translate.py -d 2 --lang ru -wm small -m ru
# or a downloaded model from vosk
python3 translate.py -d 2 --lang fr -wm tiny -m /path/to/vosk-model-fr-0.22
```

connect to the http api and get the last translations

```
const translation = await fetch('http://localhost:8999/');
```