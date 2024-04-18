import os
import json
from datetime import datetime
import requests
import zipfile
from io import BytesIO
import xml.etree.ElementTree as ET
from ReqAndAuth import mediasite
from ReqAndAuth import panopto
import codecs
import boto3
import cv2
import time

class mediasitePublish2Go():
    def checkPubResp(self):
        result = self.session.get(self.getPublishToGo, headers = ms.header)
        while result.json()['DownloadUrl'] == None:
            time.sleep(5)
            result = self.session.get(self.getPublishToGo, headers = ms.header)
        return(result.json()['DownloadUrl'])
    def __init__(self, id):
        self.id = id
        self.session = requests.Session()
        self.submitPublishToGo = ms.serverURL + "/Presentations('{0}')/SubmitPublishToGo".format(id)
        self.submitPublishToGoPubResp= self.session.post(self.submitPublishToGo, headers = ms.header)
        self.getPublishToGo = ms.serverURL + "/Presentations('{0}')/PublishToGoContent".format(id)
        self.downloadURL= self.checkPubResp()
        self.download = self.session.get(self.downloadURL, headers = ms.header)
        self.zipfile= zipfile.ZipFile(BytesIO(self.download.content))
        self.path = "MSFiles/{0}".format(self.id)
        self.zipfile.extractall(self.path)

class mediasitePresentation():
    def getSlideNumbers(self,path):
        tree = ET.parse(path+"/"+self.xml_file_names[0])
        root = tree.getroot()
        return([i.text for i in root.iter('Number')])
    def getSlideTimes(self,path):
        tree = ET.parse(path+"/"+self.xml_file_names[0])
        root = tree.getroot()
        rawTimes = [i.text for i in root.iter('Time')]
        duration =[i.text for i in root.iter('Duration')]
        rawTimes.append(duration[-1])
        exactTimes =[int(rawTimes[i+1])-int(rawTimes[i]) for i in range(len(rawTimes)-1)]
        result =[i/1000 for i in exactTimes]
        return(result)
    def makeSlideTuples(self):
        if len(self.image_stream) == len(self.xml_slide_times):
            return([(self.image_stream[i], self.xml_slide_times[i]) for i in range(len(self.xml_slide_times))])
    def makeSlideVideo(self):
        #30fps preferable for latency, though 15fps with checkRound enabled is more efficient
        fps = 30
        w, h = None, None
        for file, duration in self.slideTuples:
            frame = cv2.imread(file)
            if w is None:
                h, w, _ = frame.shape
                fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
                writer = cv2.VideoWriter(self.nextPath+"/"+'output.mp4', fourcc, fps, (w, h))
            frames2Insert=int(duration * fps)
            #frames2Insert = self.checkRound(frames2Insert)
            for repeat in range(frames2Insert):
                writer.write(frame)
        writer.release()    
    def checkRound(self,frames2Insert):
        if self.roundedLast == False:
            self.roundedLast = True
            frameInsert = int(round(frames2Insert))
        else:
            self.roundedLast = False
            frameInsert = int(frames2Insert)
        return(frameInsert)
    def __init__(self, path):
        self.nextPath= path + "/content"
        self.file_names = [file for file in os.listdir(self.nextPath) if file.endswith('.wmv')]
        self.file_names += [file for file in os.listdir(self.nextPath) if file.endswith('.mp4') if "output" not in file]
        self.file_path = self.nextPath + "/" + self.file_names[0]
        self.image_stream = sorted([self.nextPath+"/"+file for file in os.listdir(self.nextPath) if file.endswith('full.jpg')])
        self.xml_file_names = [file for file in os.listdir(path) if file.endswith('.xml')]
        self.xml_slide_numbers = self.getSlideNumbers(path)
        self.xml_slide_times = self.getSlideTimes(path)
        self.slideTuples = self.makeSlideTuples()
        self.roundedLast = False
        self.slideStream_path= self.nextPath + "/output.mp4"
        self.makeSlideVideo()

class makePanoptoFolder():
    def __init__(self, name):
        self.mainFolder ="4493b65e-3c4b-4c41-981b-b155016277fd"
        self.payload = json.dumps({"Name": name, "Description": "Folder Working?", "Parent": self.mainFolder})
        self.createFolderEndpoint = pan.serverURL + "/Panopto/api/v1/folders"
        self.createFolder = requests.post(self.createFolderEndpoint, headers = pan.header, data = self.payload)
        self.newFolderId = self.createFolder.json()['Id']

class uploadPanopto():
    def createSession(self):
        payload = json.dumps({"FolderId": self.folderId})
        self.uploadSessionResp = requests.post(pan.serverURL +"/Panopto/PublicAPI/Rest/sessionUpload", headers = pan.header, data = payload)
        self.uploadID = self.uploadSessionResp.json()['ID']
        self.uploadTarget = self.uploadSessionResp.json()['UploadTarget']
    def multipartUpload(self, uploadTarget, file_path):
        elements = uploadTarget.split('/')
        service_endpoint = '/'.join(elements[0:-2:])
        bucket = elements[-2]
        prefix = elements[-1]
        object_key = '{0}/{1}'.format(prefix, os.path.basename(file_path))
        s3 = boto3.session.Session().client(
            service_name = 's3',
            endpoint_url = service_endpoint,
            verify = False,
            aws_access_key_id='dummy',
            aws_secret_access_key = 'dummy')
        mpu = s3.create_multipart_upload(Bucket = bucket, Key = object_key)
        mpu_id = mpu['UploadId']
        self.uploadParts(file_path, bucket, object_key, mpu_id,s3)
    def uploadParts(self, file_path, bucket, object_key, mpu_id,s3):
        parts = []
        uploaded_bytes = 0
        total_bytes = os.stat(file_path).st_size
        with open(file_path, 'rb') as f:
            i = 1
            while True:
                data = f.read(self.PART_SIZE)
                if not len(data):
                    break
                part = s3.upload_part(Body = data, Bucket = bucket, Key = object_key, UploadId = mpu_id, PartNumber = i)
                parts.append({'PartNumber': i, "ETag": part['ETag']})
                uploaded_bytes += len(data)
                print('  -- {0} of {1} bytes uploaded'.format(uploaded_bytes, total_bytes))
                i += 1
        result = s3.complete_multipart_upload(Bucket = bucket, Key = object_key, UploadId = mpu_id, MultipartUpload = {"Parts": parts})
    def createManifest(self, file_path, manifest_file_name):
        file_name = os.path.basename(file_path)
        with open(self.manifestFileTemplate) as fr:
            template = fr.read()
            content = template\
            .replace('{Title}', file_name)\
            .replace('{Description}', 'This is a video session with the uploaded video file {0}'.format(file_name))\
            .replace('{Filename}', file_name)\
            .replace('{Date}', datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f-00:00'))
        with codecs.open(manifest_file_name, 'w', 'utf-8') as fw:
            fw.write(content)
    def finishUpload(self, uploadSessionResp):
        upload_id = self.uploadID
        upload_target = self.uploadTarget
        while True:
            print('Calling PUT PublicAPI/REST/sessionUpload/{0} endpoint'.format(upload_id))
            url = '{0}/Panopto/PublicAPI/REST/sessionUpload/{1}'.format(pan.serverURL, upload_id)
            payload = copy.copy(uploadSessionResp.json())
            payload['State'] = 1 # Upload Completed
            resp = requests.put(url, json = payload, headers = pan.header)
            if resp.status_code // 100 == 2:
                print('Upload completed')
                break
    def __init__(self, folderId, file_path, slideStream_path):
        self.PART_SIZE = 5 * 1024 * 1024
        self.manifestFileTemplate = 'upload_manifest_template.xml'
        self.manifestFileName = 'upload_manifest_generated.xml'
        self.folderId = folderId
        self.createSession()
        self.multipartUpload(self.uploadTarget, file_path)
        self.multipartUpload(self.uploadTarget, slideStream_path)
        self.createManifest(file_path, self.manifestFileName)
        self.multipartUpload(self.uploadTarget, self.manifestFileName)
        self.finishUpload(self.uploadSessionResp)

class prog():
    def __init__(self):
        self.id = "mediasiteID"
        ms= mediasite()
        pan = panopto()
        msp2g = mediasitePublish2Go(self.id)
        msx = mediasitePresentation(msp2g.path)
        pf = makePanoptoFolder("testUpload")
        up = uploadPanopto(pf.newFolderId, msx.file_path, msx.slideStream_path)
