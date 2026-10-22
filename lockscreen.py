from tkinter import Tk, Toplevel, Label, Entry, Button, messagebox
from queue import Queue

root = Tk()
root.title("ATLRoot")
root.withdraw()

class LockScreen(Toplevel):
    def _init_ui(self):
        self.label = Label(
            self,
            text="ACCESS SUSPENDED\nInactivity Limit Exceeded",
            fg="#e74c3c",
            bg="black",
            font=("Arial", 34, "bold"),
            justify="center"
        )
        self.label.pack(expand=True, pady=(40,20))
        
        self.lbl_remark = Label(
            self,
            text="Enter Remark (Why were you away?):",
            fg="white",
            bg="black",
            font=("Arial", 12)
        )
        self.lbl_remark.pack(pady=5)
        
        self.entry_remark = Entry(
            self,
            font=("Arial", 18),
            width=40
        )
        self.entry_remark.pack(pady=10)
        self.entry_remark.focus_set()
        
        self.btn_submit = Button(
            self,
            text="SUBMIT REMARK",
            command=self.submit_remark,
            font=("Arial", 14),
            bg="#0078d7",
            fg="white",
            padx=20
        )
        self.btn_submit.pack(pady=20)
        
        self.btn_refresh = Button(
            self,
            text="CHECK FOR APPROVAL (REFRESH)",
            command=self.check_status,
            font=("Arial", 14),
            bg="orange",
            fg="black",
            padx=20
        )
        
        self.btn_unlock = Button(
            self,
            text="CLICK HERE TO UNLOCK SYSTEM",
            command=self.hide,
            font=("Arial", 14),
            bg="green",
            fg="white",
            padx=20
        )

    def __init__(self):
        super().__init__(root)
        self.withdraw()
        #self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-fullscreen", True)
        self.configure(background='black')
        
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.grab_set()
        self.focus_force()
        
        self.callbacks = {
            "remark": None,
            "status": None,
            "hide": None,
        }
        self._init_ui()
    
    def callback(self, key) -> tuple[str, str]:
        """Run the registered callback function (if any) and return (Result, Error)"""
        if key in self.callbacks:
            if self.callbacks[key]:
                return self.callbacks[key]()
        else:
            print(f"{key} callback does not exist[LockScreen]")
        return "2", ""
    
    def add_callback(self, key, fn):
        """
        Register a callback for an event. The callback must return (Result, Error)
        Events:
            `remark`: User submitted a remark
            `status`: User refreshed the status
        """
        if key not in self.callbacks:
            print(f"{key} event does not exist [LockScreen]")
            return
        
        self.callbacks[key] = fn
  
    def submit_remark(self):
        remark = self.entry_remark.get().strip()
        
        if len(remark) < 5:
            messagebox.showwarning("Remark Required", "Please provide a valid remark.", parent=self)
            return
        
        self.btn_submit.config(state="disabled", text="Submitting...")
        res,err = self.callback("remark")
        
        if res:
            self.after(0, self.show_refresh_button)
        elif err:
            self.after(0, lambda: self.handle_submit_error(err))
    
    def show_refresh_button(self):
        self.btn_submit.pack_forget()
        self.entry_remark.config(state="disabled")
        self.btn_refresh.pack(pady=20)
        self.update_idletasks()
        
        messagebox.showinfo("Submitted", "Remark submitted succesfully.\nWait for Admin approval.", parent=self)
    
    def handle_submit_error(self, err):
        self.btn_submit.config(state="normal", text="SUBMIT REMARK")
        messagebox.showerror("Error", f"Failed to submit remark\n{err}", parent=self)
    
    def check_status(self):
        self.btn_refresh.config(state="disabled", text="Checking...")
        res,err = self.callback("status")
        
        if res:
            self.after(0, lambda: self.handle_status_result(res))
        elif err:
            self.after(0, lambda: self.handle_status_error(err))
    
    def handle_status_result(self, current_status):
        self.btn_refresh.config(state="normal", text="CHECK FOR APPROVAL (REFRESH)")
        
        if current_status == "2":
            self.btn_refresh.pack_forget()
            self.btn_unlock.pack(pady=20)
            self.update_idletasks()
            messagebox.showinfo("Approved", "Admin approved.\nYou can now unlock the system.", parent=self)
            
        elif current_status == "1":
            messagebox.showinfo("Pending", "Approval still pending.\nPlease refresh again later.", parent=self)
            
        else:
            messagebox.showwarning("Status", f"Current Status: {current_status}", parent=self)
            
    def handle_status_error(self, err):
        self.btn_refresh.config(state="normal", text="CHECK FOR APPROVAL (REFRESH)")
        messagebox.showerror("Connection Error", err, parent=self)
    
    def hide(self):
        self.withdraw()
        self.callback("hide")
    
    def show(self):
        self.deiconify()
    
    def stop(self):
        self.destroy()
        root.destroy()

class LockScreenController:
    def __init__(self):
        self.root = root
        self.name = root.title()
        self.queue = Queue()
        self.lock_screen = LockScreen()
        root.after(50, self.process_queue)
    
    def process_queue(self):
        while not self.queue.empty():
            event = self.queue.get()
            
            if event == "show":
                self.lock_screen.show()
            
            elif event == "hide":
                self.lock_screen.hide()
        
        root.after(50, self.process_queue)
    
    def show_lock_screen(self):
        self.queue.put("show")
    
    def hide_lock_screen(self):
        self.queue.put("hide")

if __name__ == "__main__":
    LockScreen().show()
    try: root.mainloop()
    except: pass