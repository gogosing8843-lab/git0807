import os
import sys
import datetime
import threading
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

# scraper 모듈 불러오기
from scraper import scrape_mois, scrape_mss, scrape_moel, save_to_excel

class NoticeCrawlerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("타기관(행안부·중기부·고용부) 사업공고 자동 수집기")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)
        
        # 스타일 및 테마 설정
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.current_excel_path = None
        self.collected_data = []
        
        self.create_styles()
        self.build_ui()
        
    def create_styles(self):
        # Color Palette
        PRIMARY_COLOR = "#1F4E78"
        SECONDARY_COLOR = "#2B5797"
        BG_COLOR = "#F4F6F9"
        TEXT_COLOR = "#333333"
        
        self.root.configure(bg=BG_COLOR)
        
        self.style.configure(".", background=BG_COLOR, foreground=TEXT_COLOR, font=("맑은 고딕", 10))
        
        # Frame
        self.style.configure("Card.TFrame", background="#FFFFFF", relief="solid", borderWidth=1)
        
        # Buttons
        self.style.configure("Primary.TButton", font=("맑은 고딕", 11, "bold"), background=PRIMARY_COLOR, foreground="#FFFFFF", padding=8)
        self.style.map("Primary.TButton", background=[("active", SECONDARY_COLOR)])
        
        self.style.configure("Secondary.TButton", font=("맑은 고딕", 10), background="#5C6BC0", foreground="#FFFFFF", padding=6)
        self.style.map("Secondary.TButton", background=[("active", "#3F51B5")])
        
        self.style.configure("Success.TButton", font=("맑은 고딕", 10, "bold"), background="#2E7D32", foreground="#FFFFFF", padding=6)
        self.style.map("Success.TButton", background=[("active", "#1B5E20")])

        # Treeview
        self.style.configure("Treeview", font=("맑은 고딕", 10), rowheight=28, background="#FFFFFF", fieldbackground="#FFFFFF")
        self.style.configure("Treeview.Heading", font=("맑은 고딕", 10, "bold"), background="#1F4E78", foreground="#FFFFFF")
        self.style.map("Treeview.Heading", background=[("active", "#163857")])

    def build_ui(self):
        # Top Header Frame
        header_frame = tk.Frame(self.root, bg="#1F4E78", height=70)
        header_frame.pack(fill="x", side="top")
        
        title_label = tk.Label(
            header_frame, 
            text="🏛️ 타기관 사업공고 자동 수집기", 
            font=("맑은 고딕", 16, "bold"), 
            fg="#FFFFFF", 
            bg="#1F4E78"
        )
        title_label.pack(side="left", padx=20, pady=15)
        
        subtitle_label = tk.Label(
            header_frame, 
            text="행정안전부 | 중소벤처기업부 | 고용노동부 (최근 30일)", 
            font=("맑은 고딕", 10), 
            fg="#D0E1F9", 
            bg="#1F4E78"
        )
        subtitle_label.pack(side="left", padx=10, pady=20)

        # Control Panel
        ctrl_frame = tk.Frame(self.root, bg="#F4F6F9", padx=15, pady=10)
        ctrl_frame.pack(fill="x", side="top")
        
        self.btn_start = ttk.Button(ctrl_frame, text="🚀 공고 데이터 수집 시작", style="Primary.TButton", command=self.start_crawling)
        self.btn_start.pack(side="left", padx=5)
        
        self.btn_open_excel = ttk.Button(ctrl_frame, text="📂 엑셀 파일 열기", style="Success.TButton", command=self.open_excel_file, state="disabled")
        self.btn_open_excel.pack(side="left", padx=5)
        
        self.btn_open_link = ttk.Button(ctrl_frame, text="🌐 선택 공고 웹페이지 열기", style="Secondary.TButton", command=self.open_selected_link)
        self.btn_open_link.pack(side="left", padx=5)
        
        # Summary Counter Cards Frame
        card_frame = tk.Frame(self.root, bg="#F4F6F9", padx=15, pady=5)
        card_frame.pack(fill="x", side="top")
        
        self.lbl_total = self.create_summary_card(card_frame, "총 수집 건수", "0 건", "#1F4E78")
        self.lbl_mois = self.create_summary_card(card_frame, "행정안전부", "0 건", "#2B5797")
        self.lbl_mss = self.create_summary_card(card_frame, "중소벤처기업부", "0 건", "#007ACC")
        self.lbl_moel = self.create_summary_card(card_frame, "고용노동부", "0 건", "#2E7D32")

        # Table (Treeview) Area
        table_frame = tk.Frame(self.root, bg="#F4F6F9", padx=15, pady=10)
        table_frame.pack(fill="both", expand=True, side="top")
        
        columns = ("dept", "title", "keywords", "reg_date", "deadline", "link")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("dept", text="지자체명")
        self.tree.heading("title", text="공고제목")
        self.tree.heading("keywords", text="매칭키워드")
        self.tree.heading("reg_date", text="등록일")
        self.tree.heading("deadline", text="마감일")
        self.tree.heading("link", text="링크")
        
        self.tree.column("dept", width=120, anchor="center")
        self.tree.column("title", width=450, anchor="w")
        self.tree.column("keywords", width=140, anchor="center")
        self.tree.column("reg_date", width=100, anchor="center")
        self.tree.column("deadline", width=120, anchor="center")
        self.tree.column("link", width=90, anchor="center")
        
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        self.tree.bind("<Double-1>", lambda event: self.open_selected_link())

        # Status & Progress Footer
        footer_frame = tk.Frame(self.root, bg="#E0E0E0", height=30, padx=10)
        footer_frame.pack(fill="x", side="bottom")
        
        self.lbl_status = tk.Label(footer_frame, text="준비됨. '공고 데이터 수집 시작' 버튼을 누르세요.", font=("맑은 고딕", 9), fg="#444444", bg="#E0E0E0")
        self.lbl_status.pack(side="left", padx=5, pady=4)
        
        self.progress = ttk.Progressbar(footer_frame, mode="indeterminate", length=150)
        self.progress.pack(side="right", padx=10, pady=4)

    def create_summary_card(self, parent, title, initial_val, color):
        card = tk.Frame(parent, bg="#FFFFFF", relief="solid", bd=1, padx=15, pady=8)
        card.pack(side="left", expand=True, fill="x", padx=5)
        
        lbl_t = tk.Label(card, text=title, font=("맑은 고딕", 9), fg="#666666", bg="#FFFFFF")
        lbl_t.pack(anchor="w")
        
        lbl_v = tk.Label(card, text=initial_val, font=("맑은 고딕", 13, "bold"), fg=color, bg="#FFFFFF")
        lbl_v.pack(anchor="e")
        return lbl_v

    def start_crawling(self):
        self.btn_start.config(state="disabled")
        self.progress.start(10)
        self.lbl_status.config(text="데이터 수집 중입니다... 잠시만 기다려 주세요.")
        
        # Clear Treeview
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Threading for non-blocking UI
        t = threading.Thread(target=self.run_crawler_thread, daemon=True)
        t.start()

    def run_crawler_thread(self):
        try:
            self.update_status("행정안전부 공고 수집 중...")
            mois_data = scrape_mois(limit_days=30)
            self.lbl_mois.config(text=f"{len(mois_data)} 건")
            
            self.update_status("중소벤처기업부 사업공고 수집 중...")
            mss_data = scrape_mss(limit_days=30)
            self.lbl_mss.config(text=f"{len(mss_data)} 건")
            
            self.update_status("고용노동부 공고 수집 중...")
            moel_data = scrape_moel(limit_days=30)
            self.lbl_moel.config(text=f"{len(moel_data)} 건")
            
            all_data = mois_data + mss_data + moel_data
            total_cnt = len(all_data)
            self.lbl_total.config(text=f"{total_cnt} 건")
            
            # 엑셀 파일 저장
            today_str = datetime.date.today().strftime("%Y%m%d")
            output_filename = f"타기관벤치마킹_{today_str}.xlsx"
            save_to_excel(mois_data, mss_data, moel_data, output_filename)
            self.current_excel_path = os.path.abspath(output_filename)
            
            # UI에 데이터 추가 (최신순 내림차순 정렬된 전체 데이터)
            from scraper import sort_by_latest
            sorted_all_data = sort_by_latest(all_data)
            self.collected_data = sorted_all_data
            
            self.root.after(0, self.populate_treeview, sorted_all_data)
            self.root.after(0, self.on_crawling_complete, total_cnt, output_filename)
            
        except Exception as e:
            self.root.after(0, self.on_crawling_error, str(e))

    def update_status(self, text):
        self.root.after(0, lambda: self.lbl_status.config(text=text))

    def populate_treeview(self, data):
        for item in data:
            self.tree.insert("", "end", values=(
                item["지자체명"],
                item["공고제목"],
                item["매칭키워드"],
                item["등록일"],
                item["마감일"],
                item["링크"]
            ))

    def on_crawling_complete(self, total_cnt, filename):
        self.progress.stop()
        self.btn_start.config(state="normal")
        self.btn_open_excel.config(state="normal")
        self.lbl_status.config(text=f"수집 완료! 총 {total_cnt}건 수집됨 ({filename} 저장됨)")
        messagebox.showinfo("수집 완료", f"총 {total_cnt}건의 사업공고 수집이 완료되었습니다.\n엑셀 파일({filename})이 생성되었습니다.")

    def on_crawling_error(self, err_msg):
        self.progress.stop()
        self.btn_start.config(state="normal")
        self.lbl_status.config(text="수집 중 오류 발생")
        messagebox.showerror("오류 발생", f"데이터 수집 중 오류가 발생했습니다:\n{err_msg}")

    def open_excel_file(self):
        if self.current_excel_path and os.path.exists(self.current_excel_path):
            try:
                os.startfile(self.current_excel_path)
            except Exception as e:
                messagebox.showerror("오류", f"엑셀 파일을 열 수 없습니다:\n{e}")
        else:
            messagebox.showwarning("경고", "생성된 엑셀 파일이 없습니다.")

    def open_selected_link(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("알림", "목록에서 공고를 선택하세요.")
            return
        
        item_vals = self.tree.item(selected_item[0], "values")
        if item_vals and len(item_vals) >= 6:
            url = item_vals[5]
            if url and url.startswith("http"):
                webbrowser.open(url)

if __name__ == "__main__":
    root = tk.Tk()
    app = NoticeCrawlerApp(root)
    root.mainloop()
