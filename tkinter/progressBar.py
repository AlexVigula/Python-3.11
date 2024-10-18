from tkinter import *
import tkinter.ttk as ttk
import time, threading
root = Tk()

pb = ttk.Progressbar(root, mode="determinate")
pb.pack()

def progress():
    for i in range(11):
        pb['value'] += i
        time.sleep(.3)

threading.Thread(target=progress).start()
root.mainloop()
