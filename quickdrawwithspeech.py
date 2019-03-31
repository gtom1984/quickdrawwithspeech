# Python
from __future__ import division
import io
import os
import re
import time
import sys

# QuickDraw
from quickdraw import QuickDrawDataGroup, QuickDrawing

# Google Cloud
from google.cloud import language, speech
from google.cloud.speech import enums
from google.cloud.speech import types

# 3rd party
import pyaudio
from six.moves import queue
import tkinter


# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

# setup canvas
WIDTH=800
HEIGHT=800
window = tkinter.Tk()
canvas = tkinter.Canvas(window, width=WIDTH, height=HEIGHT)
canvas.pack()

# drawings
all_drawings = []

# offset addition
X_OFFSET_ADD = 250


class draw_thing():
    '''
    draws and animates objects
    also stores the canvas objects to be deleted later
    '''

    def __init__(self, drawings, name, padding_x=0, padding_y=0):
        self.drawings = drawings
        self.padding_x = padding_x
        self.padding_y = padding_y

        noun_keyword_offset = {
          'fish': 200,
          'bird': -200,
        }

        # some objects are sky or below sky
        if name in noun_keyword_offset:
            self.padding_y = self.padding_y + noun_keyword_offset[name]

        self.name = name
        self.lines = []


    def animate(self):
        window.update()

        # draw them
        for i in range(0, self.drawings.drawing_count):
            time.sleep(0.05)
            self.draw(drawing=self.drawings.get_drawing(index=i))
            if i < (self.drawings.drawing_count - 1):
                self.erase()


    def draw(self, drawing=0):
        self.lines = []
        for stroke in drawing.strokes:
            x_last = 0
            y_last = 0
            index = 0
            for x, y in stroke:
                x = x + self.padding_x
                y = y + self.padding_y
                if index > 0:
                    self.lines.append(canvas.create_line(x_last,
                                                         y_last,
                                                         x,
                                                         y,
                                                         width=5,
                                                         cap=tkinter.ROUND,
                                                         join=tkinter.ROUND))
                x_last = x
                y_last = y
                index = index + 1
                window.update()


    def erase(self):
        for line_id in self.lines:
            canvas.after(50, canvas.delete, line_id)
            window.update()


def word_entities(word):
    document = language.types.Document(content=word,
                                       type=language.enums.Document.Type.PLAIN_TEXT,)
    client = language.LanguageServiceClient()
    response = client.analyze_entities(document=document,encoding_type='UTF32',)

    # get all drawings
    global all_drawings

    # erase old scene if exists
    last_x_offset = 50
    for drawing_object in all_drawings:
        drawing_object.erase()

    y_offset = (HEIGHT / 2) - 100

    # loop through words and draw
    for entity in response.entities:
        print(entity.name)
        print(entity.type)

        # special keywords can change y offset
        y_offset_keywords = {
          'above': -200,
          'below': 200,
        }

        # check if this is something to draw or a keyword to influence drawing
        if entity.name in y_offset_keywords:
            y_offset = y_offset + y_offset_keywords[entity.name]
        else:
            # lowercase all entities, uppercase will find drawings
            name = entity.name.lower()

            try:
                # get 10 drawings if they exist
                drawings = QuickDrawDataGroup(name, max_drawings=10)

                # confirm there is someting to draw
                if drawings:
                    # change padding offsets to keep drawings separate
                    padding_x = last_x_offset
                    padding_y = (HEIGHT / 2) - 100
                    drawing = draw_thing(drawings,
                                         name,
                                         padding_x=padding_x,
                                         padding_y=padding_y)
                    drawing.animate()
                    all_drawings.append(drawing)
                    last_x_offset = last_x_offset + X_OFFSET_ADD
            except ValueError:
                print("No drawings of {} in dataset".format(entity.name))


class MicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""
    def __init__(self, rate, chunk):
        self._rate = rate
        self._chunk = chunk

        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            # The API currently only supports 1-channel (mono) audio
            # https://goo.gl/z757pE
            channels=1, rate=self._rate,
            input=True, frames_per_buffer=self._chunk,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=self._fill_buffer,
        )

        self.closed = False

        return self

    def __exit__(self, type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        """Continuously collect data from the audio stream, into the buffer."""
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        while not self.closed:
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b''.join(data)


def listen_print_loop(responses):
    """Iterates through server responses and prints them.

    The responses passed is a generator that will block until a response
    is provided by the server.

    Each response may contain multiple results, and each result may contain
    multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
    print only the transcription for the top alternative of the top result.

    In this case, responses are provided for interim results as well. If the
    response is an interim one, print a line feed at the end of it, to allow
    the next result to overwrite it, until the response is a final one. For the
    final one, print a newline to preserve the finalized transcription.
    """
    num_chars_printed = 0
    for response in responses:
        if not response.results:
            continue

        # The `results` list is consecutive. For streaming, we only care about
        # the first result being considered, since once it's `is_final`, it
        # moves on to considering the next utterance.
        result = response.results[0]
        if not result.alternatives:
            continue

        # Display the transcription of the top alternative.
        transcript = result.alternatives[0].transcript

        # Display interim results, but with a carriage return at the end of the
        # line, so subsequent lines will overwrite them.
        #
        # If the previous result was longer than this one, we need to print
        # some extra spaces to overwrite the previous result
        overwrite_chars = ' ' * (num_chars_printed - len(transcript))

        if not result.is_final:
            sys.stdout.write(transcript + overwrite_chars + '\r')
            sys.stdout.flush()

            num_chars_printed = len(transcript)

        else:
            print(transcript + overwrite_chars)

            # call entity function to break transcript into objects and draw
            word_entities(transcript)

            # Exit recognition if any of the transcribed phrases could be
            # one of our keywords.
            if re.search(r'\b(exit|quit)\b', transcript, re.I):
                print('Exiting..')
                break

            num_chars_printed = 0         


def main():
    # Show canvas
    canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#ffffff")

    horizon = HEIGHT / 2 + 100
    canvas.create_line(0,
                       horizon,
                       WIDTH,
                       horizon,
                       width=2,
                       dash=(4, 4),
                       fill="#d3d3d3",
                       cap=tkinter.ROUND,
                       join=tkinter.ROUND)
    window.update()

    # See http://g.co/cloud/speech/docs/languages
    # for a list of supported languages.
    language_code = 'en-US'  # a BCP-47 language tag

    client = speech.SpeechClient()
    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code=language_code)
    streaming_config = types.StreamingRecognitionConfig(
        config=config,
        interim_results=True)

    with MicrophoneStream(RATE, CHUNK) as stream:
        audio_generator = stream.generator()
        requests = (types.StreamingRecognizeRequest(audio_content=content)
                    for content in audio_generator)

        responses = client.streaming_recognize(streaming_config, requests)

        # Now, put the transcription responses to use.
        try:
            listen_print_loop(responses)
        except Exception as ex:
            print("listen_print_loop exceptions: {}".format(ex))


if __name__ == '__main__':
    main()
