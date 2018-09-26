# Much of the OpenCV is from: https://stackoverflow.com/questions/189943/how-can-i-quantify-difference-between-two-images

import os
import random
import time
import sys
import iothub_client
import json
import cv2
import base64
import SimpleHTTPServer
import SocketServer
import thread
import socket
import commands

#from scipy.misc import imread
from scipy.linalg import norm
from scipy import sum, average

#import cv2.cv as cv
from iothub_client import IoTHubClient, IoTHubClientError, IoTHubTransportProvider
from iothub_client import IoTHubMessage, IoTHubMessageDispositionResult, IoTHubError

# messageTimeout - the maximum time in milliseconds until a message times out.
# The timeout period starts at IoTHubClient.send_event_async.
# By default, messages do not expire.
MESSAGE_TIMEOUT = 10000

# global counters
RECEIVE_CALLBACKS = 0
SEND_CALLBACKS = 0
TWIN_CALLBACKS = 0
SEND_MESSAGECOUNTER = 0

# Web Service port
WebServicePort = 8080

# how long we keep older files in seconds
keepImageFiles = 120   # one hour

# camera JSON, updated from the desired properties
cameraJSON = '{"publicURL":"rtmp://localhost:1935/live/drone"}'

# Default imageProcessing interval in seconds
imageProcessingInterval = 3

# Whether or not we conver the images to Gray Scale to eliminate color issues
imageToGrayScale = False

# Whether or not we normalize the images, for different sizes and etc
imageNormalization = False

# for our face images, add some padding in pixels
facePadding = 20

# Choose HTTP, AMQP or MQTT as transport protocol.  Currently only MQTT is supported.
PROTOCOL = IoTHubTransportProvider.MQTT

# Whether or not we do face detection
faceDetection = False

# String containing Hostname, Device Id & Device Key & Module Id in the format:
# "HostName=<host_name>;DeviceId=<device_id>;SharedAccessKey=<device_key>;ModuleId=<module_id>;GatewayHostName=<gateway>"
CONNECTION_STRING = "[Device Connection String]"

# Callback received when the message that we're forwarding is processed.
def send_confirmation_callback(message, result, user_context):
    global SEND_CALLBACKS
    print ( "  Confirmation[%d] received for message with result = %s" % (user_context, result) )
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    #print ( "    Properties: %s" % key_value_pair )
    SEND_CALLBACKS += 1
    #print ( "    Total calls confirmed: %d" % SEND_CALLBACKS )

# receive_message_callback is invoked when an incoming message arrives on the specified 
# input queue (in the case of this sample, "input1").  Because this is a filter module, 
# we will forward this message onto the "output1" queue.
def receive_message_callback(message, hubManager):
    global RECEIVE_CALLBACKS
    message_buffer = message.get_bytearray()
    size = len(message_buffer)
    print ( "    Data: <<<%s>>> & Size=%d" % (message_buffer[:size].decode('utf-8'), size) )
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print ( "    Properties: %s" % key_value_pair )
    RECEIVE_CALLBACKS += 1
    print ( "    Total calls received: %d" % RECEIVE_CALLBACKS )
    hubManager.forward_event_to_output("output1", message, 0)
    return IoTHubMessageDispositionResult.ACCEPTED

def to_grayscale(arr):
    "If arr is a color image (3D array), convert it to grayscale (2D array)."
    if len(arr.shape) == 3:
        return average(arr, -1)  # average over the last axis (color channels)
    else:
        return arr

def normalize(arr):
    rng = arr.max()-arr.min()
    amin = arr.min()
    return (arr-amin)*255/rng

def compare_images(img1, img2):
    try:
        # normalize to compensate for exposure difference
        if imageNormalization:
            img1 = normalize(img1)
            img2 = normalize(img2)
        
        # calculate the difference and its norms
        diff = img1 - img2  # elementwise for scipy arrays
        m_norm = sum(abs(diff))  # Manhattan norm
        z_norm = norm(diff.ravel(), 0)  # Zero norm
        return (m_norm, z_norm)
    except:
        return (0.0, 0.0)

def startWebService():
    Handler = SimpleHTTPServer.SimpleHTTPRequestHandler
    httpd = SocketServer.TCPServer(("", WebServicePort), Handler)

    print ("Listening for remote connections on port:", WebServicePort)
    httpd.serve_forever()

class HubManager(object):

    def __init__(
            self,
            connection_string):
        self.client_protocol = PROTOCOL
        self.client = IoTHubClient(connection_string, PROTOCOL)
        
        # set the time until a message times out
        self.client.set_option("messageTimeout", MESSAGE_TIMEOUT)
        # some embedded platforms need certificate information
        self.set_certificates()
        
        # sets the callback when a message arrives on "input1" queue.  Messages sent to 
        # other inputs or to the default will be silently discarded.
        self.client.set_message_callback("input1", receive_message_callback, self)

        # start the background web service
        thread.start_new_thread(startWebService, ())

    def set_certificates(self):
        isWindows = sys.platform.lower() in ['windows', 'win32']
        if not isWindows:
            CERT_FILE = os.environ['EdgeModuleCACertificateFile']        
            print("Adding TrustedCerts from: {0}".format(CERT_FILE))
            
            # this brings in x509 privateKey and certificate
            file = open(CERT_FILE)
            try:
                self.client.set_option("TrustedCerts", file.read())
                print ( "set_option TrustedCerts successful" )
            except IoTHubClientError as iothub_client_error:
                print ( "set_option TrustedCerts failed (%s)" % iothub_client_error )

            file.close()

    # Forwards the message received onto the next stage in the process.
    def forward_event_to_output(self, outputQueueName, event, send_context):
        self.client.send_event_async(
            outputQueueName, event, send_confirmation_callback, send_context)

def main(connection_string):
    global SEND_MESSAGECOUNTER

    try:
        print ( "\nPython %s\n" % sys.version )
        print ( "IoT Hub Client for Python" )
        print ("mounted: ", commands.getstatusoutput('mount | grep video'))
        print ("classify: ", commands.getstatusoutput('ls -all /usr/share/opencv/haarcascades/haarcascade_frontalface_alt.xml'))

        hub_manager = HubManager(connection_string)

        print ( "Starting the IoT Hub Python sample using protocol %s..." % hub_manager.client_protocol )

        face_cascade = cv2.CascadeClassifier('/usr/share/opencv/haarcascades/haarcascade_frontalface_alt.xml')

        # We only have one camera
        cameraArray = json.loads(cameraJSON)
        cameraName = "publicURL"
        cameraURL = cameraArray[cameraName]
        myIP = socket.gethostbyname(socket.gethostname()) # will be the module's IP address

        print ( "Capturing from: ", cameraURL )
        vcap = cv2.VideoCapture(cameraURL)

        priorFrame = None

        while True:
            try:
                # removing old files
                #print ( "Removing old files")
                now = time.time()
                for f in os.listdir("."):
                    if "-image.jpg" in f:
                        fullpath = os.path.join(".", f)
                        if os.stat(fullpath).st_mtime < (now - keepImageFiles):
                            if os.path.isfile(fullpath):
                                print ( "Removing old file: ", fullpath )
                                os.remove(fullpath)

                filename = str(cameraName + '-' + time.strftime('%Y-%m-%d-%H-%M-%S') +'-image.jpg')

                #print ( "Reading frame")
                isFrameAvailable, frame = vcap.read()
                
                if frame is None:
                    print ("No frame captured, skipping")
                    break
                    
                else:
                    #print ( "Saving current frame to captures/current.jpg")
                    cv2.imwrite("captures/current.jpg", frame)

                    #print ( "Will compare to prior frames")
                    if priorFrame is None:
                        # we don't have a prior image, must be the first time we saw this camera or TWIN change
                        ManhattanImageChange = 0.0
                        ZeroImageChange = 0.0

                        # naming and writing the image file
                        #print ( "No prior frame. Saving initial frame to captures/"+filename)
                        cv2.imwrite("captures/"+filename, frame)

                        # store the current frame for comparison
                        priorFrame = frame
                        
                    else:
                        #print ( "There is a prior frame")

                        if imageToGrayScale:
                            img1 = to_grayscale(priorFrame.astype(float))
                            img2 = to_grayscale(frame.astype(float))
                        else:
                            img1 = priorFrame.astype(float)
                            img2 = frame.astype(float)                   
                        
                        #print ( "Comparing images to get ManhattanImageChange and ZeroImageChange")
                        n_m, n_0 = compare_images(img1, img2)
                        ManhattanImageChange = n_0*1.0/frame.size
                        ZeroImageChange = n_m*1.0/frame.size

                        #print ( "ManhattanImageChange: ", ManhattanImageChange)
                        #print ( "ZeroImageChange: ", ZeroImageChange)

                        # naming and writing the image file
                        print ( "Saving frame to captures/"+filename)
                        cv2.imwrite("captures/"+filename, frame)

                    # reading and encoding the file for the JSON message
                    #print ( "Reading and encoding the file for the JSON message")
                    with open("captures/"+filename, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read())
                    
                    # creating the JSON for the IoTMessage
                    IoTMessageJSON = {}

                    if faceDetection:
                        try:
                            IoTMessageJSON['faces'] = 0
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            #print ( "Running face detection on the frame")
                            faces = face_cascade.detectMultiScale(gray, 1.1, 5)
                        except:
                            faces = None
                            e = sys.exc_info()[0]
                            print ( "Error with face recognition %s" % e )
                        
                        if faces is not None:
                            #print ("Found ", str(len(faces)), " face(s)")
                            IoTMessageJSON['faces'] = len(faces)
                            IoTMessageJSON['faceUrls'] = [] # initialize the urls nested array with number of faces detected
                            faceCounter = 0
                            for (x,y,w,h) in faces:
                                #print ("Drawing rectangle on face")
                                cv2.rectangle(frame,(x,y),(x+w,y+h),(255,0,0),2)
                                facefilename = str('face-' + str(faceCounter) + '-' + cameraName + '-' + time.strftime('%Y-%m-%d-%H-%M-%S') +'-image.jpg')
                                print ( "Saving face to captures/"+facefilename)
                                cv2.imwrite("captures/"+facefilename,frame[y-facePadding:y+h+facePadding, x-facePadding:x+w+facePadding])
                                #print ("Storing face in array")
                                IoTMessageJSON['faceUrls'].append(str("http://" + myIP + ":" + str(WebServicePort) + "/" + facefilename))
                                #IoTMessageJSON['face' + str(faceCounter) + cameraName + 'URL'] = str("http://" + myIP + ":" + str(WebServicePort) + "/" + facefilename)
                                faceCounter += 1
                            
                            framefilename = str(cameraName + '-' + time.strftime('%Y-%m-%d-%H-%M-%S') +'-frame-image.jpg')
                            IoTMessageJSON['framedImageURL'] = str("http://" + myIP + ":" + str(WebServicePort) + "/" + framefilename)
                            print ( "Saving framed faces to captures/"+framefilename)
                            cv2.imwrite("captures/"+framefilename, frame)

                    #IoTMessageJSON['imageBase64'] = encoded_string
                    
                    IoTMessageJSON['cameraURL'] = cameraURL
                    IoTMessageJSON['imageSize'] = os.path.getsize("captures/"+filename)
                    IoTMessageJSON['imageFileName'] = "captures/"+filename
                    IoTMessageJSON['imageURL'] = str("http://" + myIP + ":" + str(WebServicePort) + "/" + filename)
                    IoTMessageJSON['GrayScale'] = imageToGrayScale
                    IoTMessageJSON['Normalized'] = imageNormalization
                    IoTMessageJSON['ManhattanImageChange'] = ManhattanImageChange 
                    IoTMessageJSON['ModuleIPAddress'] = str(myIP)
                    IoTMessageJSON['ZeroImageChange'] = ZeroImageChange
                    IoTMessageJSON['dateTime'] = time.strftime('%Y-%m-%dT%H:%M:%S')

                    IoTMessage = IoTHubMessage(bytearray(json.dumps(IoTMessageJSON), 'utf8'))

                    hub_manager.forward_event_to_output("output1", IoTMessage, SEND_MESSAGECOUNTER)

                    print ("sent: ", json.dumps(IoTMessageJSON))
                    SEND_MESSAGECOUNTER += 1


                # Sleep for the image processing interval
                print ("Sleeping for seconds: " , imageProcessingInterval)
                print ()

                time.sleep(imageProcessingInterval)

            except: # catch *all* exceptions
                e = sys.exc_info()[0]
                print ( "Unexpected error in while cameraChange == False loop %s" % e )
    
    except IoTHubError as iothub_error:
        # Release video capture device
        vcap.release()
        print ( "Unexpected error %s from IoTHub" % iothub_error )
        return
    except KeyboardInterrupt:
        print ( "IoTHubClient sample stopped" )

if __name__ == '__main__':
    try:
        CONNECTION_STRING = os.environ['EdgeHubConnectionString']

    except Exception as error:
        print ( error )
        sys.exit(1)

    main(CONNECTION_STRING)
    
