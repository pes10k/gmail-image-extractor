import Tkinter
import Tkconstants
tk = Tkinter.Tk()

frame = Tkinter.Frame(tk, relief=Tkconstants.RIDGE, borderwidth=2)
frame.pack(fill=Tkconstants.BOTH, expand=1)
label = Tkinter.Label(frame, text="Hello, World")
label.pack(fill=Tkconstants.X, expand=1)
button = Tkinter.Button(frame, text="Exit", command=tk.destroy)
button.pack(side=Tkconstants.BOTTOM)
tk.mainloop()
