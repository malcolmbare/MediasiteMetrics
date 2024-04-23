from ReqAndAuth import mediasite
import time
import torch
from transformers import AutoProcessor, Wav2Vec2BertForCTC
import soundfile as sf
import wordninja
from spellwise import Levenshtein
from transformers import pipeline
from pydub import AudioSegment
import requests
import os

class modelsAndDependencies():
    def loadVadModel(self):
        self.vadModel, self.utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                              model='silero_vad',
                              force_reload=True,
                              onnx=False) # perform `pip install -q onnxruntime` and set this to True, if you want to use ONNX
        self.getSpeechTimeStamps, self.saveAudio, self.readAudio, self.VADIterator, self.collectChunks = self.utils
    def loadWav2Vec2Model(self):
        self.wav2Vectokenizer = AutoProcessor.from_pretrained("hf-audio/wav2vec2-bert-CV16-en")
        self.wav2VecModel = Wav2Vec2BertForCTC.from_pretrained("hf-audio/wav2vec2-bert-CV16-en")
    def openEngDict(self):
        with open("american-english.txt", "r") as file:
            eng_dictionary = file.read().splitlines()
        return(eng_dictionary)
    def __init__(self):
        self.ms = mediasite()
        self.loadVadModel()
        self.loadWav2Vec2Model()
        self.engDict = self.openEngDict()
        self.levenshtein = Levenshtein()
        self.levenshtein.add_from_path("american-english.txt")

class mediasiteCC():
    def checkPubResp(self):
        result = self.session.get(self.getCC, headers = mad.ms.header)
        while result.json()['value'][0]['DownloadUrl'] == None:
            time.sleep(5)
            result = self.session.get(self.getCC, headers = mad.ms.header)
        return(result.json()['value'][0]['DownloadUrl'])
    def __init__(self, id):
        self.id = id
        self.session = requests.Session()
        self.getCC = mad.ms.serverURL + "/Presentations('{0}')/PodcastContent".format(id)
        self.getCCResp= self.session.get(self.getCC, headers = mad.ms.header)
        self.downloadURL= self.checkPubResp()
        self.download = self.session.get(self.downloadURL, headers = mad.ms.header)
        self.filename = str(id)+".mp3"
        with open(self.filename,"wb") as f:
            f.write(self.download.content)
        self.wavFilename = str(id)+".wav"
        sound = AudioSegment.from_mp3(self.filename)
        sound.export(self.wavFilename, format="wav")
        

class wavFile():
    def splitWav(self):
        result = []
        for i in range(self.splitFileCount):
            start = self.speech_timestamps[i]['start']
            end = self.speech_timestamps[i]['end']
            result.append(self.wav[start:end])
        return(result)
    def makeSplitFileNames(self):
        return(["{0}/{1}_{2}.wav".format(self.path2splitFiles,self.filenameNoExt,i) for i in range(self.splitFileCount)])
    def makeWavDir(self):
        os.makedirs(self.path2splitFiles, exist_ok=True)
    def writeSplitFiles(self):
        for i in range(self.splitFileCount):
            sf.write(self.splitFilenames[i], self.splitFiles[i], 16000)
    def checkSpeechTimestamps(self):
        result = []
        for i in self.speech_timestamps:
            if i['end'] - i['start'] > 1000000:
                denominator = 2
                while (i['end'] - i['start'])/denominator > 1000000:
                    denominator += 1
                for j in range(denominator):
                    result.append({"start": int(i['start'] + (i['end'] - i['start'])/denominator * j), "end": int(i['start'] + (i['end'] - i['start'])/denominator * (j+1))})
            else:
                result.append(i)
        return(result)
    def __init__(self,path2file):
        self.path2file = path2file
        self.filename = path2file.split("/")[-1]
        self.filenameNoExt = self.filename.split(".")[0]
        self.path2splitFiles= os.path.expanduser("~/Desktop") +"/".join(path2file.split("/")[:-1]) + "/{0}_splitFile".format(self.filenameNoExt)
        print(self.path2splitFiles)
        self.makeWavDir()
        self.wav = mad.readAudio(self.filename, sampling_rate=16000)
        print("Getting timestamps")
        self.speech_timestamps = mad.getSpeechTimeStamps(self.wav, mad.vadModel, sampling_rate=16000)
        print("Completed")
        print(len(self.speech_timestamps))
        self.speech_timestamps = self.checkSpeechTimestamps()
        print(len(self.speech_timestamps))
        self.splitFileCount = len(self.speech_timestamps)
        self.splitFiles = self.splitWav()
        self.splitFilenames = self.makeSplitFileNames()
        self.writeSplitFiles()

class rawTranscription():
    def loadWav(self,path2file):
        wav,sr = sf.read(path2file)
        return(wav)
    def transribe(self,wav):
        wavLen= len(wav)
        inputs= mad.wav2Vectokenizer(wav,sampling_rate=16000,return_tensors="pt")
        with torch.no_grad():
            logits = mad.wav2VecModel(**inputs).logits
        predicted_ids = torch.argmax(logits, dim=-1)
        transcription = mad.wav2Vectokenizer.batch_decode(predicted_ids)
        print(transcription)
        self.transcription[self.lastWavLen] = transcription
        self.lastWavLen += wavLen
    def makeTranscription(self):
        for i in self.splitFileNames:
            wav = self.loadWav(i)
            self.transribe(wav)
    def __init__(self, splitFileNames):
        self.splitFileNames = splitFileNames
        self.lastWavLen = 0
        self.transcription = {}
        self.makeTranscription()

class chunkTranscription():
    def chunkTranscription(self):
        result = []
        tally = 0
        currentChunk = []
        for item in list(self.rt.values()):
            if tally < self.chunkSize + len(item[0]):
                currentChunk.append(item[0])
                tally += len(item[0])
            else:
                result.append(" ".join(currentChunk))
                currentChunk = []
                tally = 0
                currentChunk.append(item[0])
                tally += len(item[0])
        result.append(" ".join(currentChunk))
        return(result)
    def __init__(self, rt):
        self.rt = rt.transcription
        self.chunkSize = 3000
        self.chunks = self.chunkTranscription()

class cleanTranscription():
    def makeTokens(self):
        result =[]
        for chunk in self.chunks:
            for token in chunk.split():
                result.append(token)
        return(result)
    def makeSCBow(self):
        self.spelledCorrectlyBow = [i for i in self.bow if i in self.spelledCorrectly]
    def makeSIBow(self):
        self.spelledIncorrectlyBow = [i for i in self.bow if i in self.spelledIncorrectly]
    def splitPass(self):
        for i in self.spelledIncorrectly:
            if len([word for word in wordninja.split(i) if word in self.eng_dictionary]) == len(wordninja.split(i)):
                self.corrections[i] = wordninja.split(i)
                self.spelledIncorrectly.remove(i)
            elif len(i) > 12:
                self.corrections[i] = wordninja.split(i)
                self.spelledIncorrectly.remove(i)
    def splitPass2(self):
        for i in self.spelledIncorrectly:
            splitWord = wordninja.split(i)
            count=0
            for word in splitWord:
                suggestions = mad.levenshtein.get_suggestions(word)
                if len(suggestions)>0:
                    if suggestions[0]['distance'] ==0:
                        count+=1
            if count == len(splitWord):
                self.corrections[i] = splitWord
                self.spelledIncorrectly.remove(i)
    def levPass(self):
        for i in self.spelledIncorrectly:
            if i not in self.corrections.keys():
                suggestions = mad.levenshtein.get_suggestions(i)
                safeSuggestions = [i for i in suggestions if i['word'] in self.spelledCorrectly]
                sortedSuggestions = sorted(safeSuggestions, key=lambda x: x["distance"])
                if len(sortedSuggestions)>0:
                    if sortedSuggestions[0]["distance"]<2:
                        self.corrections[i] = sortedSuggestions[0]["word"]
                        self.spelledIncorrectly.remove(i)
    def makeCorrectedChunks(self):
        result = []
        for chunk in self.chunks:
            newChunk = []
            for token in chunk.split():
                if token in self.corrections.keys():
                    if type(self.corrections[token]) == list:
                        newChunk += self.corrections[token]
                    else:
                        newChunk.append(self.corrections[token])
                else:
                    newChunk.append(token)
            result.append(" ".join(newChunk))
        return(result)
    def startProcess(self):
        self.makeSCBow()
        self.makeSIBow()
        self.corrections = {}
        print("Incorrect Tokens: " +str(len(self.spelledIncorrectlyBow)))
        self.splitPass()
        self.makeSIBow()
        print("Split Pass 1 Completed")
        print("Incorrect Tokens: " +str(len(self.spelledIncorrectlyBow)))
        self.levPass()
        self.makeSIBow()
        print("Levenshtein Pass Completed")
        print("Incorrect Tokens: " +str(len(self.spelledIncorrectlyBow)))
        self.splitPass2()
        self.makeSIBow()
        print("splitPass2 Completed")
        print("Incorrect Tokens: " +str(len(self.spelledIncorrectlyBow)))
    def __init__(self, chunks):
        self.chunks = chunks
        self.bow = self.makeTokens()
        self.vocabulary = list(set(self.bow))
        self.eng_dictionary = mad.engDict
        self.spelledCorrectly =[i for i in self.vocabulary if i in self.eng_dictionary]
        self.spelledIncorrectly = [i for i in self.vocabulary if i not in self.eng_dictionary]
        self.startProcess()
        self.correctedChunks = self.makeCorrectedChunks()

class basicSummarizer():
    def summarize(self, chunks):
        result =[]
        for chunk in chunks:
            summary =self.summarizer(chunk, max_length=130, min_length=30, do_sample=False)[0]['summary_text']
            print(summary)
            result.append(summary)
        return(result)
    def chunkSummary(self):
        result = []
        tally = 0
        currentChunk = []
        for item in list(self.summaries):
            if tally < self.chunkSize + len(item[0]):
                currentChunk.append(item[0])
                tally += len(item[0])
            else:
                result.append(" ".join(currentChunk))
                currentChunk = []
                tally = 0
                currentChunk.append(item[0])
                tally += len(item[0])
        result.append(" ".join(currentChunk))
        return(result)   
    def __init__(self, correctedChunks):
        self.chunkSize = 3000
        self.summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
        self.summaries = self.summarize(correctedChunks)
        self.summary = " ".join(self.chunkSummary())
     

mad = modelsAndDependencies()
mediasite_get_wav = mediasiteCC(id)
split_wav = wavFile(mediasite_get_wav.wavFilename)
raw_transcription = rawTranscription(split_wav.splitFilenames)
chunked_transcription = chunkTranscription(raw_transcription)
cleaned_trascription = cleanTranscription(chunked_transcription.chunks)
basic_summary = basicSummarizer(cleaned_trascription.correctedChunks)
print(basic_summary.summary)
