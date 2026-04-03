
import gradio as gr, pandas as pd, qrcode, os, re, smtplib
from zipfile import ZipFile
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from email.message import EmailMessage

EVENT_NAME  = "GRAND EVENT 2026"
EVENT_DATE  = "10 April 2026"
EVENT_TIME  = "6:00 PM"
EVENT_VENUE = "City Convention Centre, Lahore"
EMAIL_SENDER   = os.getenv("EMAIL_SENDER",   "your_email@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "your_app_password")

ticket_store = {}

def is_valid_email(e):
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", e.strip()))

def generate_ticket_pdf(name, ticket_id, seat):
    pdf_path = f"/tmp/{ticket_id}.pdf"
    c = canvas.Canvas(pdf_path, pagesize=letter)
    w, h = letter
    c.setFillColorRGB(0.07,0.18,0.52); c.rect(0,h-110,w,110,fill=1)
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",24)
    c.drawString(50,h-55,EVENT_NAME)
    c.setFont("Helvetica",12)
    c.drawString(50,h-80,f"{EVENT_DATE}  |  {EVENT_TIME}  |  {EVENT_VENUE}")
    c.setFillColorRGB(0.97,0.97,0.97); c.setStrokeColorRGB(0.07,0.18,0.52)
    c.rect(40,190,w-80,310,fill=1)
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica",12)
    c.drawString(60,448,f"Name      :  {name}")
    c.drawString(60,428,f"Ticket ID :  {ticket_id}")
    c.drawString(60,408,f"Seat      :  {seat}")
    c.drawString(60,388,f"Date      :  {EVENT_DATE}")
    c.drawString(60,368,f"Time      :  {EVENT_TIME}")
    c.drawString(60,348,f"Venue     :  {EVENT_VENUE}")
    c.setDash(4,4); c.line(40,330,w-40,330); c.setDash()
    qr = qrcode.make(ticket_id)
    qr_path = f"/tmp/{ticket_id}_qr.png"; qr.save(qr_path)
    c.drawImage(qr_path,w-185,340,130,130)
    c.setFont("Helvetica-Oblique",9); c.drawString(w-175,332,"Scan at entry gate")
    c.setFillColorRGB(0.07,0.18,0.52); c.rect(0,0,w,50,fill=1)
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica",10)
    c.drawString(50,18,"Non-transferable. Valid for one entry only.")
    c.save(); return pdf_path

def send_ticket_email(receiver, name, pdf_path):
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Your Ticket for {EVENT_NAME}"
        msg["From"] = EMAIL_SENDER; msg["To"] = receiver
        msg.set_content(f"Dear {name},\n\nThank you for registering!\nDate: {EVENT_DATE}\nTime: {EVENT_TIME}\nVenue: {EVENT_VENUE}\n\nYour ticket is attached.\n\nBest regards,\nEvent Team")
        with open(pdf_path,"rb") as f:
            msg.add_attachment(f.read(),maintype="application",subtype="pdf",filename=f"ticket_{name}.pdf")
        with smtplib.SMTP_SSL("smtp.gmail.com",465) as smtp:
            smtp.login(EMAIL_SENDER,EMAIL_PASSWORD); smtp.send_message(msg)
        return "Sent"
    except Exception as e:
        return f"Failed: {e}"

def process_csv(file):
    if file is None: return None,"⚠️ Upload a CSV first."
    try: df = pd.read_csv(file.name)
    except Exception as e: return None,f"❌ {e}"
    df.columns = df.columns.str.strip()
    col_map = {c.lower():c for c in df.columns}
    if "name" not in col_map: return None,"❌ CSV must have a Name column."
    name_col = col_map["name"]; seat_col = col_map.get("seat"); email_col = col_map.get("email")
    zip_path = "/tmp/tickets.zip"; log = []; ticket_store.clear()
    with ZipFile(zip_path,"w") as zipf:
        for i,row in df.iterrows():
            name = str(row[name_col]).strip()
            seat = str(row[seat_col]).strip() if seat_col else f"AUTO-{i+1:03d}"
            email = str(row[email_col]).strip() if email_col else ""
            tid = f"TICKET-{i+1:04d}"
            ticket_store[tid] = {"name":name,"seat":seat,"email":email,"used":False}
            pdf = generate_ticket_pdf(name,tid,seat)
            zipf.write(pdf,arcname=f"{tid}_{name}.pdf"); os.remove(pdf)
            qp = f"/tmp/{tid}_qr.png"
            if os.path.exists(qp): os.remove(qp)
            if email and is_valid_email(email):
                s = send_ticket_email(email,name,pdf); log.append(f"  {name} → {email}: {s}")
            else: log.append(f"  {name} → No email")
    return zip_path, f"✅ {len(df)} tickets generated!\n\n📧 Log:\n"+"\n".join(log)

def send_single_email(tid,email_override):
    tid = tid.strip().upper()
    if tid not in ticket_store: return f"❌ {tid} not found."
    info = ticket_store[tid]
    email = email_override.strip() or info["email"]
    if not email or not is_valid_email(email): return "❌ No valid email."
    pdf = generate_ticket_pdf(info["name"],tid,info["seat"])
    s = send_ticket_email(email,info["name"],pdf); os.remove(pdf)
    return f"✅ Sent to {info['name']} at {email}" if s=="Sent" else f"❌ {s}"

def verify_ticket(tid):
    tid = tid.strip().upper()
    if not tid: return "⚠️ Enter a Ticket ID."
    if tid not in ticket_store: return "❌ Invalid — not found."
    if ticket_store[tid]["used"]: return f"❌ Already Used — {ticket_store[tid]['name']}."
    ticket_store[tid]["used"] = True
    i = ticket_store[tid]
    return f"✅ Valid\nName: {i['name']}\nSeat: {i['seat']}\nID: {tid}"

def chatbot_response(message, history):
    msg = message.lower().strip()
    m = re.search(r"(?:send|email|resend).*?(ticket-\d+)(?:.*?to\s+([\w\.\-]+@[\w\.\-]+))?",msg)
    if m:
        tid = m.group(1).upper(); email_to = m.group(2)
        if tid not in ticket_store: return f"❌ {tid} not found."
        info = ticket_store[tid]; email = email_to or info["email"]
        if not email or not is_valid_email(email): return f"⚠️ No email for {tid}. Try: send ticket {tid} to x@gmail.com"
        pdf = generate_ticket_pdf(info["name"],tid,info["seat"])
        s = send_ticket_email(email,info["name"],pdf); os.remove(pdf)
        return f"✅ Sent to {info['name']} at {email}!" if s=="Sent" else f"❌ {s}"
    if any(k in msg for k in ["list tickets","show tickets","all tickets"]):
        if not ticket_store: return "📭 No tickets yet. Upload CSV first."
        return "📋 Tickets:\n"+"\n".join([f"• {tid} — {i['name']} | {i['seat']} | {'✅ Used' if i['used'] else '🟢 Valid'}" for tid,i in ticket_store.items()])
    c = re.search(r"(ticket-\d+)",msg)
    if c:
        tid = c.group(1).upper()
        if tid in ticket_store:
            i = ticket_store[tid]
            return f"🎟 {tid}\nName: {i['name']}\nSeat: {i['seat']}\nStatus: {'Used ❌' if i['used'] else 'Valid ✅'}"
        return f"❌ {tid} not found."
    if any(k in msg for k in ["send all","email all"]):
        if not ticket_store: return "📭 No tickets yet."
        results=[]
        for tid,i in ticket_store.items():
            if i["email"] and is_valid_email(i["email"]):
                pdf=generate_ticket_pdf(i["name"],tid,i["seat"]); s=send_ticket_email(i["email"],i["name"],pdf); os.remove(pdf)
                results.append(f"• {i['name']} → {s}")
            else: results.append(f"• {i['name']} → Skipped")
        return "📧 Bulk Email:\n"+"\n".join(results)
    if "event" in msg: return f"📅 {EVENT_NAME}\nDate: {EVENT_DATE}\nTime: {EVENT_TIME}\nVenue: {EVENT_VENUE}"
    if "date" in msg: return f"📆 {EVENT_DATE}"
    if "time" in msg: return f"⏰ {EVENT_TIME}"
    if "venue" in msg or "where" in msg: return f"📍 {EVENT_VENUE}"
    if any(k in msg for k in ["help","hi","hello"]):
        return "👋 Commands:\n• list tickets\n• TICKET-0001 — check ticket\n• send ticket TICKET-0001\n• send ticket TICKET-0001 to x@gmail.com\n• send all\n• Ask: date, time, venue"
    return "🤖 Type help to see all commands."

with gr.Blocks(title="Smart Event Ticket System PRO") as app:
    gr.Markdown(f"# 🎟️ Smart Event Ticket System (PRO)\n**{EVENT_NAME}** · {EVENT_DATE} · {EVENT_TIME}")
    with gr.Tab("📂 Generate Tickets"):
        gr.Markdown("Upload CSV: **Name, Seat, Email**")
        csv_input=gr.File(label="Upload CSV",file_types=[".csv"])
        gen_btn=gr.Button("⚡ Generate & Email Tickets",variant="primary")
        zip_output=gr.File(label="📦 Download ZIP")
        gen_log=gr.Textbox(label="📋 Log",lines=8)
        gen_btn.click(process_csv,inputs=csv_input,outputs=[zip_output,gen_log])
    with gr.Tab("📧 Send Email Manually"):
        me_ticket=gr.Textbox(label="Ticket ID",placeholder="TICKET-0001")
        me_email=gr.Textbox(label="Email Override (optional)")
        me_btn=gr.Button("📤 Send Email",variant="primary")
        me_result=gr.Textbox(label="Result")
        me_btn.click(send_single_email,inputs=[me_ticket,me_email],outputs=me_result)
    with gr.Tab("✅ Verify Ticket"):
        v_input=gr.Textbox(label="Ticket ID",placeholder="TICKET-0001")
        v_btn=gr.Button("🔍 Verify",variant="primary")
        v_output=gr.Textbox(label="Result",lines=4)
        v_btn.click(verify_ticket,inputs=v_input,outputs=v_output)
    with gr.Tab("🤖 AI Chatbot"):
        gr.Markdown("**Try:** `list tickets` · `send ticket TICKET-0001` · `send all`")
        chatbot=gr.ChatInterface(fn=chatbot_response,
            examples=["Hello","list tickets","send ticket TICKET-0001","send all","What is the event date?"])

app.launch()
