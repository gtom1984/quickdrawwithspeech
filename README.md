# quickdrawwithspeech
Simple python script using Google Speech APIs and QuickDraw to convert speech into simple drawings  

**Installation**  

Prerequisite:  
Python 3.5+  

Then use pip to install the following packages.  
google-api-core==1.8.0  
google-auth==1.6.3  
google-cloud-language==1.1.1  
google-cloud-speech==0.36.3  
googleapis-common-protos==1.5.8  
quickdraw==0.1.0  
PyAudio==0.2.11  

Setup the Google Speech API keys using this guide (the **Setting up authentication** section explains):  https://cloud.google.com/speech-to-text/docs/reference/libraries#client-libraries-install-python

This will require a Google Cloud account to access the APIs.  This script works fine with the standard environment variable keys.

Then download **quickdrawwithspeech.py** and run it.  A canvas should appear and it will draw a simple scene when you speak.
