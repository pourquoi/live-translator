import argparse
import queue
import sys
import sounddevice as sd
import numpy as np
import os
import threading
import json
from colorama import Fore, Style
from http.server import BaseHTTPRequestHandler, HTTPServer

import whisper
from scipy.io.wavfile import write
from vosk import Model, KaldiRecognizer
import argostranslate.package
import argostranslate.translate

q = queue.Queue()
q2 = queue.Queue()
q3 = queue.Queue(maxsize=30)


class ApiServer(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        try:
            content = q3.get(block=False)
        except queue.Empty:
            content = ''

        # print(f'api response: sending {content}')

        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(bytes(json.dumps(content), "utf-8"))

    def log_message(self, format, *args):
        return

class DataBuffer:
    buffer = np.zeros((0, 1))


buffer = DataBuffer()


def serve_forever(httpd):
    with httpd:
        httpd.serve_forever()


def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


def callback(indata, frames, time, status):
    npdata = np.frombuffer(indata, dtype="int16")
    npdata = npdata.reshape((npdata.shape[0], 1))
    buffer.buffer = np.concatenate((buffer.buffer, npdata))
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))


def whisper_translate(model, samplerate, lang):
    while True:
        data = q2.get(block=True)
        if data is not None:
            print(f'queue size={q2.qsize()}, data shape={data.shape}')
            write('buffer.wav', samplerate, data)
            if lang == "en":
                result = model.transcribe('buffer.wav', fp16=False, language='en', task='transcribe')
                print(f'transcribed: {Fore.GREEN}{result["text"]}{Style.RESET_ALL}')
            else:
                #result = model.transcribe('buffer.wav', fp16=False, language=lang, task='transcribe')
                #print(f'transcribed: {Fore.WHITE}{result["text"]}{Style.RESET_ALL}')
                result = model.transcribe('buffer.wav', fp16=False, language=lang, task='translate')
                print(f'translated: {Fore.GREEN}{result["text"]}{Style.RESET_ALL}')
            os.remove('buffer.wav')


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    "-l", "--list-devices", action="store_true",
    help="show list of audio devices and exit")
args, remaining = parser.parse_known_args()
if args.list_devices:
    print(sd.query_devices())
    parser.exit(0)
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    parents=[parser])
parser.add_argument(
    "-f", "--filename", type=str, metavar="FILENAME",
    help="audio file to store recording to")
parser.add_argument(
    "-d", "--device", type=int_or_str,
    help="input device (numeric ID or substring)")
parser.add_argument(
    "-r", "--samplerate", type=int, help="sampling rate")
parser.add_argument(
    "-m", "--model", type=str, help="language model; e.g. en-us, fr, nl; default is en-us")
parser.add_argument(
    "-wm", "--wmodel", type=str, help="whisper model; e.g. small, small.en")
parser.add_argument(
    "-lang", "--lang", type=str, help="audio lang; e.g en, fr")

args = parser.parse_args(remaining)

try:
    if args.samplerate is None:
        device_info = sd.query_devices(args.device, "input")
        print(device_info)
        # soundfile expects an int, sounddevice provides a float:
        args.samplerate = int(device_info["default_samplerate"])

    if args.model is None:
        model = Model(lang="en-us")
    else:
        if args.model.startswith('/'):
            model = Model(model_path=args.model)
        else:
            model = Model(lang=args.model)

    if args.wmodel is None:
        whisper_model = whisper.load_model('small.en')
    else:
        whisper_model = whisper.load_model(args.wmodel)

    if args.lang is None:
        lang = 'en'
    else:
        lang = args.lang

    if lang != 'en':
        from_code = lang
        to_code = "en"
        argostranslate.package.update_package_index()
        available_packages = argostranslate.package.get_available_packages()
        package_to_install = next(
            filter(
                lambda x: x.from_code == from_code and x.to_code == to_code, available_packages
            )
        )
        argostranslate.package.install_from_path(package_to_install.download())

    # uncomment to test whisper
    #x = threading.Thread(target=whisper_translate, args=(whisper_model, args.samplerate, lang), daemon=True)
    #x.start()

    httpd = HTTPServer(('localhost', 8999), ApiServer)
    x2 = threading.Thread(target=serve_forever, args=(httpd,), daemon=True)
    x2.start()

    with sd.RawInputStream(samplerate=args.samplerate, blocksize=8000, device=args.device,
                dtype="int16", channels=1, callback=callback):
        print("#" * 80)
        print("Press Ctrl+C to stop the recording")
        print("#" * 80)

        rec = KaldiRecognizer(model, args.samplerate)
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if result['text'] != '':
                    print(f'{result["text"]}')

                    if lang != 'en':
                        translatedText = argostranslate.translate.translate(result["text"], lang, 'en')
                        print(f'{Fore.GREEN}{translatedText}{Style.RESET_ALL}')
                        print('')
                        if translatedText != '':
                            q3.put({"translated": translatedText, "original": result["text"]})

                    # uncomment to test whisper
                    # q2.put(np.copy(buffer.buffer))

                buffer.buffer = np.zeros((0, 1))
            else:
                # print(rec.PartialResult())
                pass

except KeyboardInterrupt:
    if os.path.exists('buffer.wav'): os.remove('buffer.wav')
    print("\nDone")
    parser.exit(0)

except Exception as e:
    if os.path.exists('buffer.wav'): os.remove('buffer.wav')
    print(type(e).__name__ + ": " + str(e))
    parser.exit(1)
