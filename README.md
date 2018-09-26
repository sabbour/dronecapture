# README

Based on [https://github.com/ksaye/IoTDemonstrations/tree/master/IoTEdgeOpenCV](https://github.com/ksaye/IoTDemonstrations/tree/master/IoTEdgeOpenCV)

Docker Image: sabbour/dronecapture

You’ll need to set an environment variable called `EdgeHubConnectionString` in the form of `"HostName=<host_name>;DeviceId=<device_id>;SharedAccessKey=<device_key>;ModuleId=<module_id>;GatewayHostName=<gateway>"` to be able to use it as a module.

The code is also expecting an RTMP stream to be sent at `rtmp://localhost:1935/live/drone`

The code sends a message to the EdgeHub on `output1` with the following content. `172.17.0.2` will be the IP of the module, determined during runtime.

```json
{
   "ManhattanImageChange":0.85972543724279837,
   "ZeroImageChange":7.0326221707818934,
   "Normalized":false,
   "GrayScale":false,
   "imageSize":120876,
   "ModuleIPAddress":"172.17.0.2",
   "imageFileName":"captures/publicURL-2018-09-26-04-52-00-image.jpg,
   "imageURL":"http://172.17.0.2:8080/publicURL-2018-09-26-04-52-00-image.jpg",
   "cameraURL":"rtmp://localhost:1935/live/drone",
   "dateTime":"2018-09-26T04:52:01"
}
```

You can also include the Base64 encoded image in the message by uncommenting `IoTMessageJSON['imageBase64'] = encoded_string` line.