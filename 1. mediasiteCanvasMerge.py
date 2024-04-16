
import csv
import os
import json
from datetime import datetime
import requests
from collections import Counter
from canvAnalytics import program
from ReqAndAuth import mediasite
from ReqAndAuth import canvas

#General
def readTermDates():
    result ={}
    with open('termDatesGS.tsv', 'r') as file:
        reader = csv.reader(file, delimiter='\t')
        next(reader, None)
        for row in reader:
            term = row[0]
            startOfTerm = datetime.fromisoformat(row[1])
            endOfTerm = datetime.fromisoformat(row[2])
            result[(startOfTerm,endOfTerm)]=term
    return(result)


#Canvas Objects
class canvasDataImport():
    def makeTermYears(self):
        result = []
        for year in self.years:
            for term in self.terms:
                result.append(term + str(year))
        return(result)
    def buildQuarterD(self):
        result={}
        for term in self.termYears:
            res = program(term)
            res.addUsers()
            result[term] =res.courseList
        return(result)
    def __init__(self):
        #Terms and years can be edited if future quarters need to be added.
        self.terms = ["Summer "]
        self.years = [2016]
        self.termYears = self.makeTermYears()
        self.quarters = self.buildQuarterD()

class canvasDataImportSaveLoad():
    def checkFiles(self):
        if "canvasCourseData.json" in os.listdir():
            return(self.loadCanvasData())
        else:
            self.startImport()
    def serializeCanvasDataImport(self,cd):
        result={}
        for quarter in cd.quarters.keys():
            quarterDict={}
            for course in cd.quarters[quarter]:
                teacherDict = self.updateUserDict(course.users.teachers)
                studentDict = self.updateUserDict(course.users.students)
                taDict = self.updateUserDict(course.users.tas)
                quarterDict = self.updateQuarterDict(course,quarterDict,teacherDict,studentDict,taDict)
            result[quarter] = quarterDict
        self.data = result
    def updateUserDict(self, dict):
        result = {}
        for key in dict:
            result[str(key.id)] = {"id": key.id, "name": key.name, "login_id": key.login_id, "sortable_name": key.sortable_name}
        return(result)
    def updateQuarterDict(self,course,quarterDict,teacherDict,studentDict,taDict):
        quarterDict[course.id] = {
                    "id": course.id,
                    "name": course.name,
                    "start_at": course.start_at,
                    "end_at": course.end_at,
                    "students": studentDict,
                    "tas": taDict,
                    "teachers": teacherDict}
        return(quarterDict)
    def saveCanvasData(self):
        with open('canvasCourseData.json', 'w') as fp:
            json.dump(self.data, fp)
    def loadCanvasData(self):
        with open('canvasCourseData.json') as fp:
            return(json.load(fp))
    def startImport(self):
        cd = canvasDataImport()
        self.serializeCanvasDataImport(cd)
        self.saveCanvasData()
    def saveCanvasData(self):
        with open('canvasCourseData.json', 'w') as fp:
            json.dump(self.data, fp)
    def __init__(self):
        self.checkFiles()
        
class canvasDirectories():
    def getCourses(self):
        result = []
        for term in self.termYears:
            for course in self.quarters[term]:
                result.append(self.quarters[term][course])
        return(result)
    def checkResult(self,user,result,category, course):
        if user["id"] in result:
            if category in result[user["id"]].keys():
                result[user["id"]][category] += [course["id"]]
            else:
                result[user["id"]][category] = [course["id"]]
        else:
            result[user["id"]] = {category: [course["id"]], "userInfo": user}
        return(result)
    def buildUserDir(self):
        result ={}
        for course in self.courses:
            for user in course['students']:
                result = self.checkResult(course['students'][user],result,"enrolledAsStudent",course)
            for user in course['tas']:
                result = self.checkResult(course['tas'][user],result,"enrolledAsTA",course)
            for user in course['teachers']:
                result = self.checkResult(course['teachers'][user],result,"enrolledAsTeacher",course)
        return(result)
    def buildCourseDir(self):
        return{course['id']: course for course in self.courses}
    def buildCourseNamesDir(self):
        return({self.courseDir[courseID]['name']: self.courseDir[courseID] for courseID in self.courseDir})
    def buildUserCNetDir(self):
        return({self.userDir[userID]["userInfo"]['login_id']: self.userDir[userID] for userID in self.userDir})
    def buildTeacherNameDir(self):
        return({self.userDir[userID]["userInfo"]["sortable_name"].split(",")[0]: self.userDir[userID] for userID in self.userDir if "enrolledAsTeacher" in self.userDir[userID].keys()})
    def __init__(self, canvasDataImportObj):
        self.termYears = list(canvasDataImportObj.data.keys())
        self.quarters = {i:canvasDataImportObj.data[i] for i in self.termYears}
        self.courses = self.getCourses()
        self.userDir = self.buildUserDir()
        self.cnetDir = self.buildUserCNetDir()
        self.courseDir= self.buildCourseDir()
        self.courseNameDir = self.buildCourseNamesDir()
        self.teacherNameDir = self.buildTeacherNameDir()
        self.teacherLNCourseDir = self.buildTeacherLNCourseDir()

#Mediasite Objects
class mediasiteDataImport():
    def mediasiteGet(self,extension):
        resp = self.session.get(extension, headers = self.mediasiteConnection.header)
        if 'value' in resp.json().keys():
            result = resp.json()['value']
            currentResult = resp.json()
            if 'odata.nextLink' in currentResult.keys():
                self.updateResult(result, currentResult)
            else:
                return(result)
        else:
            return(resp.json())  
        return(result)
    def updateResult(self,result, currentResult):
        nextLink =currentResult['odata.nextLink']
        while 'odata.nextLink' in currentResult.keys():    
            nextLink = currentResult['odata.nextLink']
            print(nextLink)
            resp = self.session.get(nextLink, headers = self.mediasiteConnection.header)
            result+= resp.json()['value']
            currentResult = resp.json()
        resp = self.session.get(nextLink, headers = self.mediasiteConnection.header)
        result+= resp.json()['value']
        return(result)
    def buildPresentationDir(self):
        result ={}
        for presentation in self.presentationsBase:
            id = presentation['Id']
            result[id] = {"basic":presentation}
            result[id]['analytics'] = self.mediasiteGet(self.mediasiteConnection.serverURL+"/"+"PresentationAnalytics('{0}')".format(id))
            result[id]['viewingSessions']= self.mediasiteGet(self.mediasiteConnection.serverURL+"/"+"PresentationAnalytics('{0}')/ViewingSessions".format(id))
            result[id]['users'] = self.mediasiteGet(self.mediasiteConnection.serverURL+"/"+"PresentationAnalytics('{0}')/Users".format(id))
            print(presentation['Title'] + " Metrics Logged")
        return(result)
    def __init__(self):
        self.mediasiteConnection = mediasite()
        self.session = requests.Session()
        self.presentationsBase = self.mediasiteGet(self.mediasiteConnection.serverURL+"/"+"Presentations?$select=full")
        self.presentationDir=self.buildPresentationDir()

class mediasiteDataImportSaveLoad():
    def loadMediaSiteData(self):
        with open('mediaSiteData.json') as fp:
            return(json.load(fp))
    def checkFiles(self):
        if "mediaSiteData.json" in os.listdir():
            self.data =self.loadMediaSiteData()
        else:
            self.startImport()
    def saveMediaSiteData(self):
        with open('mediaSiteData.json', 'w') as fp:
            json.dump(self.data, fp)
    def startImport(self):
        md = mediasiteDataImport()
        self.data = md.presentationDir
        self.saveMediaSiteData()
    def __init__(self):
       self.checkFiles()

class mediasiteDirectories():
    def checkResult(self,user,result,category, course):
        if user["Id"] in result:
            if category in result[user["Id"]].keys():
                result[user["Id"]][category] = result[user["Id"]][category] +[course]
            else:
                result[user["Id"]][category] = [course]
        else:
            lookupName = user["Id"]
            if "@" in user["Id"]:
                lookupName = user["Id"].split("@")[0]
            result[user["Id"]] = {"userInfo":user,"lookupName":lookupName ,category: [course]}
        return(result)
    def buildUserDir(self):
        result ={}
        for presentation in self.presentationMetrics:
            for user in self.presentationMetrics[presentation]['users']:
                result = self.checkResult(user,result,"presentationsWatched",presentation)
        return(result)
    def buildQuarterDir(self):
        result = {}
        for presentation in self.presentationMetrics:
            key= self.checkTerm(self.presentationMetrics[presentation])
            if key in result.keys():
                result[key] += [{self.presentationMetrics[presentation]['basic']['Id']: self.presentationMetrics[presentation]}]
            else:
                result[key] = [{self.presentationMetrics[presentation]['basic']['Id']: self.presentationMetrics[presentation]}]
        return(result)
    def checkTerm(self,presentation):
        for term in termDates.keys():
            dateRecorded = datetime.fromisoformat(presentation['basic']['RecordDate'])
            if dateRecorded > term[0] and dateRecorded < term[1]:
                return(termDates[term])
        return("Intersession " + str(dateRecorded.month)+ " " + str(dateRecorded.year))
    def buildUserCNetDir(self):
        return({self.userDir[userID]["lookupName"]: self.userDir[userID] for userID in self.userDir})
    def __init__(self, mediasiteDataImportObj):
        self.presentationMetrics = mediasiteDataImportObj.data
        self.quarters = self.buildQuarterDir()
        self.userDir = self.buildUserDir()
        self.cnetDir = self.buildUserCNetDir()

class mediasitePresentation():
    def checkQuarter(self,date):
        for term in termDates.keys():
            if date > term[0]:
                if date < term[1]:
                    return(termDates[term])
        return("Unknown")
    def checkViewsInQuarter(self,presentationMetricsEntry):
        if self.quarterRecorded =="Unknown":
            pass
        else:
            result = 0
            for i in presentationMetricsEntry['viewingSessions']:
                dateViewed= datetime.strptime(i['Opened'][:10],"%Y-%m-%d")
                if self.checkQuarter(dateViewed) == self.quarterRecorded:
                    result +=1
            return(result)
    def checkDatesViewed(self,presentationMetricsEntry):
        result = []
        if self.views != 0:
            for i in presentationMetricsEntry['viewingSessions']:
                dateViewed= datetime.strptime(i['Opened'][:4],"%Y")
                result.append(dateViewed.strftime("%Y"))
        return(result)
    def checkViewers(self,presentationMetricsEntry):
        result = []
        for i in presentationMetricsEntry['users']:
            for j in range(i['TotalViews']):
                result.append(i['Id'])
        return(result)
    def scoreRelevance(self):
        if self.views == 0 or self.viewsInQuarter == None:
            return(0)
        else:
            return(self.viewsInQuarter/self.views)
    def checkPercentageWatched(self,presentationMetricsEntry):
        result =[]
        for i in presentationMetricsEntry['users']:
            result.append(i['PercentWatched'])
        return(result)
    def checkPercentWatchedAVG(self):
        if len(self.percentWatched) >0:
            return(sum(self.percentWatched)/len(self.percentWatched))    
    def checkQuarter(self,date):
        for term in termDates.keys():
            if date > term[0]:
                if date < term[1]:
                    return(termDates[term])
        return("Unknown")
    def checkViewsInQuarter(self,presentationMetricsEntry):
        if self.quarterRecorded =="Unknown":
            pass
        else:
            result = 0
            for i in presentationMetricsEntry['viewingSessions']:
                dateViewed= datetime.strptime(i['Opened'][:10],"%Y-%m-%d")
                if self.checkQuarter(dateViewed) == self.quarterRecorded:
                    result +=1
            return(result)
    def checkDatesViewed(self,presentationMetricsEntry):
        result = []
        if self.views != 0:
            for i in presentationMetricsEntry['viewingSessions']:
                dateViewed= datetime.strptime(i['Opened'][:4],"%Y")
                result.append(dateViewed.strftime("%Y"))
        return(result)    
    def checkViewerIDs(self,presentationMetricsEntry):
        result = []
        for user in presentationMetricsEntry['users']:
            result.append(user['Id'].split("@")[0])
        return(result)
    def checkViewsOnOrAfter2020(self,presentationMetricsEntry):
        result = 0
        for i in presentationMetricsEntry['viewingSessions']:
            dateViewed= datetime.strptime(i['Opened'][:10],"%Y-%m-%d")
            if dateViewed > datetime.fromisoformat("2020-01-01"):
                result +=1
        return(result)
    def __init__(self, presentationMetricsEntry):
        self.id = presentationMetricsEntry['basic']['Id']
        self.title =presentationMetricsEntry['basic']['Title']
        self.views = presentationMetricsEntry['basic']['NumberOfViews']
        self.duration = presentationMetricsEntry['basic']['Duration']
        self.filesize = presentationMetricsEntry['basic']['TotalFileLength']
        self.viewers = self.checkViewers(presentationMetricsEntry)
        self.viewerIDs= self.checkViewerIDs(presentationMetricsEntry)
        self.uniqueViews = len(set(self.viewerIDs))
        self.viewsOnOrAfter2020= self.checkViewsOnOrAfter2020(presentationMetricsEntry)
        self.dateRecorded =datetime.fromisoformat(presentationMetricsEntry['basic']['RecordDate'])
        self.quarterRecorded= self.checkQuarter(self.dateRecorded)
        self.datesViewed = self.checkDatesViewed(presentationMetricsEntry)
        self.datesViewsDict=Counter(self.datesViewed)
        self.percentWatched = self.checkPercentageWatched(presentationMetricsEntry)
        self.percentWatchedAvg= self.checkPercentWatchedAVG()
        self.viewsInQuarter = self.checkViewsInQuarter(presentationMetricsEntry)
        self.relevance= self.scoreRelevance()
        self.archivalWorth=self.views*self.relevance

class mediasiteVideoTitleParse():
    def splitTitle(self):
        if "-" in self.videoTitle:
            splitTitle = self.videoTitle.split("-")
            result = [i.strip() for i in splitTitle if len(i)>0]
            return(result)
        else:
            return([self.videoTitle])
    def makeTightTitle(self):
        result = self.videoTitle
        punctuation = ["-", "(", ")", ":"]
        for mark in punctuation:
            result = self.videoTitle.replace(mark," ")
        result=' '.join(result.split())
        return(result)
    def __init__(self, rowFromCSV):
        self.videoTitle = rowFromCSV
        self.splitVideoTitle = self.splitTitle()
        self.tightTitle=self.makeTightTitle()
        self.tokens = self.tightTitle.split()
        self.tokensLower = [i.lower() for i in self.tokens]

class title2Metadata():
    def checkTerm(self,term):
        if term in self.remainingTokens:
            del self.remainingTokens[self.remainingTokens.index(term)]
            return(term)
    def checkTermPhrase(self,termPhrase):
        result = []
        terms = termPhrase.split()
        for term in terms:
            if term in self.remainingTokens:
                result.append(term)
        if len(result) ==len(terms):
            for hit in result:
                self.checkTerm(hit)
            return(" ".join(result))  
    def checkTermsAndPhrases(self,termsPhrases):
        result=[]
        terms = termsPhrases[0]
        phrases = termsPhrases[1]
        for phrase in phrases:
            if self.checkTermPhrase(phrase) != None:
                result.append(phrase)
        for term in terms:
            if self.checkTerm(term) != None:
                result.append(term)
        result = [i for i in result if len(i)>0]
        if len(result)>0:
            return("-".join(result))
    def checkDate(self):
        for token in self.remainingTokens:
            if token[0].isdigit():
                if len([i for i in token if i == "/"]) == 2:
                    del self.remainingTokens[self.remainingTokens.index(token)]
                    return(token)
    def __init__(self, tokensLower,canvasDataImport):
        self.originalTokens = tokensLower.copy()
        self.remainingTokens = self.originalTokens.copy()
        self.presentationTermsPhrases = [["presentations", "presentation", "keynote", "pitches"], ["student presentations","phd presentations", "undergrad presentations", "fireside chat"]]
        self.presentationType = self.checkTermsAndPhrases(self.presentationTermsPhrases)
        self.sessionTermsPhrases = [["session","kickoff","demo","demo,","workshop","class","review","practicum","roundtable", "keynote", "conference", "interview", "winterview", "training", "seminar"], ["round table", "focus group"]]
        self.sessionType = self.checkTermsAndPhrases(self.sessionTermsPhrases)
        self.xpTerms = ["exp25", "exp24", "axp19", "axp18", "exp26", "exp23", "axp20","xp88", "xp85" "exp", "axp", "xp", "exp20", "axp17"]
        self.nvcTerms =["nvc","cnvc","snvc", "gnvc","anvc"]
        self.eventOwnerPhrases = [["fmc","emba","polsky","rustandy", "center","execed", "careers"]+self.xpTerms+self.nvcTerms, ["new venture","fama miller", "career services", "executive education", "exec edu", "career advisor"]]
        self.eventOwnerType = self.checkTermsAndPhrases(self.eventOwnerPhrases)
        self.harperRooms = ["c01", "c02", "c03", "c04","c05", "c06", "c07", "c08", "c09", "c10", "c25", "104", "219", "3a","3b"]
        self.gleacherRooms = ["100", "200", "203", "204", "206", "208","300","302", "303","304","306","308","400","402","404","406",
                              "408", "422", "600","621"]
        self.gleacherRooms +=["gl"+i for i in self.gleacherRooms]
        self.fourFiftyFiveRooms= ["130","132","140"]
        self.locationPhrases= [self.harperRooms+ self.gleacherRooms+ self.fourFiftyFiveRooms +["gleacher", "harper", "london", "455", "hk", "campus"], ["hong kong"]]
        self.locationType= self.checkTermsAndPhrases(self.locationPhrases)
        self.courseTitlesFull = [i.lower() for i in list(canvasDataImport.courseNameDir.keys())]
        self.courseNumbers = [i.split()[1] for i in self.courseTitlesFull if i.startswith("busn")]
        self.courseTerms = [" ".join(i.split()[3:5]).replace("(","").replace(")","").strip() for i in self.courseTitlesFull if i.startswith("bus")]
        self.courseTitle =[i[i.index(")")+2:].strip() for i in self.courseTitlesFull if i.startswith("busn") and "(" in i]
        self.courseType = self.checkTermsAndPhrases([self.courseNumbers, self.courseTitle])
        self.teacherTerms = [i.lower() for i in list(canvasDataImport.teacherNameDir.keys()) if "-" not in i]
        self.teacherPhrases =[self.teacherTerms, [i.lower() for i in list(canvasDataImport.teacherNameDir.keys())  if "-" in i]]
        self.teacherType = self.checkTermsAndPhrases(self.teacherPhrases)
        self.recordingTermsPhrases = [["recording", "test", "record", '700kbps', 'default'], ["do not delete", "hold for dean's office", "backup", "guest speaker", "live stream","video slides template mp4 only"]]
        self.recordingType = self.checkTermsAndPhrases(self.recordingTermsPhrases)
        self.quarterTerms = ["spring", "summer", "autumn", "winter"]
        self.timeTerms = ["am", "pm", "week", "day"]
        self.yearTerms = ["2016", "2017", "2018", "2019", "2020"]
        self.timeType= self.checkTermsAndPhrases([self.quarterTerms + self.timeTerms + self.yearTerms, ["week " + str(i) for i in range(1, 11)]])
        self.date = self.checkDate()
        self.score= len(self.remainingTokens)/len(self.originalTokens)
        self.row = [self.presentationType, self.sessionType, self.courseType, self.timeType, self.date, self.eventOwnerType, self.locationType, self.teacherType, self.recordingType, self.score, " ".join(self.originalTokens), " ".join(self.remainingTokens)]

#Combine Directories, make CSV Ready
class mediaSiteCanvasInterchange():
    def mergeUserDir(self):
        result ={}
        for user in self.mediasiteDirectories.cnetDir:
            if user in self.canvasDirectories.cnetDir.keys():
                result[user] = {"mediaSite":self.mediasiteDirectories.cnetDir[user], "canvas":self.canvasDirectories.cnetDir[user]}
        return(result)
    def makeSharedQuarters(self):
        result ={}
        for quarter in self.mediasiteDirectories.quarters:
            if quarter[1:-1] in self.canvasDirectories.quarters.keys():
                result[quarter] = quarter[1:-1]
        return(result)
    def findCourseHits(self, presentationObj, courseDir):
        result = []
        for teacher in self.canvasDirectories.teacherNameDir.keys():
            if teacher.lower() in presentationObj.title.lower():
                result += [item for item in self.canvasDirectories.teacherNameDir[teacher]['enrolledAsTeacher'] if item in courseDir]
        return(result)
    def findCourseCandidates(self):
        result ={}
        for quarter in self.sharedQuarters.items():
            courseDir = [int(i) for i in list(self.canvasDirectories.quarters[quarter[1]].keys())]
            for presentation in self.mediasiteDirectories.quarters[quarter[0]]:
                presentationObj = mediasitePresentation(presentation[list(presentation.keys())[0]])
                hits = self.findCourseHits(presentationObj, courseDir)
                result[presentationObj.id] = hits
        return(result)
    def buildRows(self):
        result =[]
        for quarter in self.mediasiteDirectories.quarters:
            for presentation in self.mediasiteDirectories.quarters[quarter]:
                pkey = list(presentation.keys())[0]
                presentation = presentation[pkey]
                mp = mediasitePresentation(presentation)
                presentationID = mp.id
                presentationTitle = mp.title
                presentationViews = mp.views
                presentationFileSize = mp.filesize
                presentationViewers = len(mp.viewers)
                presentationUniqueViewers = mp.uniqueViews
                presentationViewsOnOrAfter2020 = mp.viewsOnOrAfter2020
                presentationDate= mp.dateRecorded
                presentationQuarter= mp.quarterRecorded
                presentationDuration = mp.duration
                presentationFolder = presentation['basic']['ParentFolderName']
                viewsInQuarter = mp.viewsInQuarter
                relevance = mp.relevance
                archivalWorth = mp.archivalWorth
                row = [presentationID, presentationTitle, presentationViews, presentationUniqueViewers,presentationViewsOnOrAfter2020, presentationFileSize, presentationViewers, presentationDate, presentationQuarter, presentationDuration, presentationFolder, viewsInQuarter, relevance, archivalWorth]
                result.append(row)
        return(result)
    def buildCourseRows(self):
        result =[]
        for row in self.baseRows:
            if row[0] in self.courseCandidate.keys():
                courseNames =[]
                teacherNames =[]
                taNames=[]
                for course in self.courseCandidate[row[0]]:
                    courseNames.append(self.canvasDirectories.courseDir[course]['name'])
                    for teacher in self.canvasDirectories.courseDir[course]['teachers']:
                        teacherNames.append(self.canvasDirectories.courseDir[course]['teachers'][teacher]['name'])
                    for ta in self.canvasDirectories.courseDir[course]['tas']:
                        taNames.append(self.canvasDirectories.courseDir[course]['tas'][ta]['name'])
                courseName = ",".join(courseNames)
                teacherName = ",".join(teacherNames)
                taName = ",".join(taNames)
                result.append(row + [courseName, teacherName, taName])
            else:
                result.append(row + ["N/A", "N/A", "N/A"])
        return(result)
    def buildGuessRows(self):
        result =[]
        for row in self.courseRows:
            title = row[1]
            t2m = title2Metadata(mediasiteVideoTitleParse(title).tokensLower, self.canvasDirectories)
            result.append(row + t2m.row)
        return(result)
    def __init__(self, mediasiteDirectoriesObj,canvasDirectoriesObj):
        self.mediasiteDirectories = mediasiteDirectoriesObj
        self.canvasDirectories = canvasDirectoriesObj
        self.sharedQuarters = self.makeSharedQuarters()
        self.userDir = self.mergeUserDir()
        self.courseCandidate = self.findCourseCandidates()
        self.baseRows = self.buildRows()
        self.courseRows = self.buildCourseRows()
        self.guessRows = self.buildGuessRows()
        
class __main__():
    termDates = readTermDates()
    md = mediasiteDataImportSaveLoad()
    cd = canvasDataImportSaveLoad()
    mdd = mediasiteDirectories(md)
    cdd = canvasDirectories(cd)
    mxc = mediaSiteCanvasInterchange(mdd,cdd)




