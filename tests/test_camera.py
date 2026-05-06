from builtins import input
import pyopenlab
import pyopenlab.instrument.camera.opencv

if __name__ == '__main__':
    device = int(eval(input("Enter the number of the camera to use: ")))
    cam = pyopenlab.instrument.camera.opencv.OpenCVCamera(device)
    cam.live_view = True
    cam.show_gui()
    cam.live_view = False
    cam.close()
    pyopenlab.close_current_datafile()

