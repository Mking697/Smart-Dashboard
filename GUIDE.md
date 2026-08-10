# 📘 Guide Book — AI Smart Dashboard

> Ye guide un logon ke liye hai jinhe data analysis nahi aata. Aapko sirf apni
> Excel file ya Google Sheet chahiye — baaki sab app khud karta hai.
> Screen par jo bhi button/label likha hai, is guide me wo `is tarah` dikhaya gaya hai.

---

## Ye app karta kya hai?

Aap apni sheet dete ho. App usse padhta hai, ganda data saaf karta hai, aur khud
se **8 ready-made reports** bana deta hai — har report ek business sawaal ka jawaab
deti hai, aur har chart ke neeche saaf English me likha hota hai ki *isse kaise
padhna hai* aur *iska matlab kya hai*.

Aapko koi formula, pivot table ya chart setting nahi seekhni.

---

## Shuru karne se pehle

| Kya chahiye | Zaruri hai? |
|---|---|
| Excel (`.xlsx`) ya CSV file, **ya** Google Sheet ka link | Haan — ya bina file ke **`✨ Try it with sample data`** dabao |
| Internet | ✅ Haan (AI aur Google Sheet ke liye) |
| Gemini API key (`.env` file me) | Optional — sirf AI features ke liye |

**Live app:** https://autolyst.online — browser me kholo, bas.

Apne computer par chalana ho to:

```bash
streamlit run app.py
```

Browser me khulega: **http://localhost:8501**

---

# Part 0 — Account banao (sirf ek baar)

App kholte hi **Log in** screen aayegi. Pehli baar aaye ho to account banana padega.

## Signup — ek hi baar

1. **`Create a new account`** dabao
2. Bharo:
   - **Your name** — aapka naam
   - **Email** — asli email daalna, ispar code aayega
   - **Password** — kam se kam **8 characters**
   - **Confirm password** — wahi password dobara
3. **`Create account`** dabao

## Email par aaye code se verify karo

Aapke email par **6 digit ka code** aayega. Wo box me daalkar
**`Verify and continue`** dabao.

| Situation | Kya karo |
|---|---|
| Email nahi aaya | **Spam folder** dekho — verification mails aksar wahin jaate hain |
| 10 minute nikal gaye | Code expire ho gaya. **`Resend code`** dabao |
| Galat code daal diya | 5 baar tak try kar sakte ho, phir naya code lena padega |
| Email galat likh diya | **`Use a different email`** dabao |

> ⏱️ Ek code bhejne ke baad agla code **60 second** baad hi bhej sakte ho.

## Ab hamesha login

Verify hone ke baad bas **email + password** se login karo. Signup dobara nahi karna.

| Problem | Solution |
|---|---|
| "Email or password is incorrect" | Dono dobara check karo. Ye message dono cases me same aata hai — security ke liye |
| "Too many failed attempts" | 5 galat koshishon ke baad account **15 minute** ke liye lock ho jata hai. Bas wait karo |
| "This email is not verified yet" | Signup hua tha par code nahi daala. **`Enter my code`** dabao |

Login hone ke baad sidebar me upar aapka naam dikhega, aur **`Log out`** ka button.

> 🔒 Aapka password kabhi save nahi hota — sirf uska ek hash rakha jata hai, jisse
> password wapas nikala nahi ja sakta.

---

# Part 1 — Pehli baar use karna (5 steps)

## Step 1 — Data source chuno

Page par upar **`Data Source`** dikhega, do options ke saath:

- **`📁 Upload File`** — apne computer se Excel/CSV upload karo
- **`🔗 Google Sheet (Live Sync)`** — Google Sheet ka link daal kar live data lao

### Agar file upload kar rahe ho

1. **`Upload your Excel or CSV file here`** par click karke file chuno.
2. Agar Excel me ek se zyada sheet hai, **`📑 Choose View Mode:`** aayega:
   - **`Specific Sheets (Custom Select)`** — aap khud chuno kaunsi sheets
   - **`All Sheets (Combine All)`** — saari sheets ek saath
3. **`☑️ Select sheets to process:`** me sheets add/remove kar sakte ho.

### Agar Google Sheet use kar rahe ho

1. Sheet ka poora link paste karo (browser ke address bar wala).
2. **`🔄 Sync Now`** dabao.
3. **Public sheet** (Anyone with the link → Viewer) ke liye bas itna hi kaafi hai.
4. **Private sheet** ke liye **`🔒 Private sheet? Connect a Google Service Account (optional)`**
   kholo, apni service account JSON key upload karo, aur jo email dikhe usse
   apni sheet **Viewer** banakar share kar do. Phir dobara `🔄 Sync Now`.

> 💡 Data har 5 minute me refresh hota hai. Turant naya data chahiye to
> `🔄 Sync Now` dubara daba do.

---

## Step 2 — Cleaning report padho

Data aate hi ek box khulega:

> **🧹 Data cleaned — using 98 row(s) that actually contain data (2 empty or junk row(s) skipped)**

Isme saaf likha hota hai app ne kya-kya hataya:

- Poori khaali rows
- Sirf `END` / `Total` likhi hui footer rows
- Aisi rows jisme sirf ID hai, baaki kuch nahi
- `N/A`, `-`, `NULL` jaise placeholder — inhe khaali maana gaya
- Extra spaces (`" Noida"` aur `"Noida"` ab ek hi jagah)

**Ye important kyun hai:** agar aapki sheet me 1000 rows hain par data sirf 100 me
hai, to app sirf un 100 par kaam karega. Baaki 900 khaali rows aapke totals kharab
nahi karengi.

> ⚠️ Agar yahan **duplicate rows** ka warning aaye, to samjho aapke totals do baar
> gin rahe hain. Source sheet me theek karo, phir dobara upload karo.

---

## Step 3 — Row rules samjho (sidebar me)

Left sidebar me **`🧹 Which rows count?`** section hai, do switches ke saath:

| Switch | Kya karta hai | Kab band karo |
|---|---|---|
| **`First column must have a value`** | Pehla column key hota hai (Order ID, Invoice No). Wahan blank = ye record hi nahi | Jab aapke pehle column me jaan-boojh kar blank hote hain |
| **`Skip nearly-empty rows`** | Jis row me sirf ID hai aur baaki sab khaali — wo record nahi mani jayegi | Jab aapko har row chahiye, chahe khaali ho |

Dono by default **ON** hain. Ek bhi switch badalte hi reports turant update ho jati hain.

> 💡 App khud safety rakhta hai: agar koi rule aadhi se zyada rows hata raha ho, to
> wo apne aap ruk jata hai — taaki galti se aapka poora data delete na ho.

---

## Step 4 — Do raste chuno

Ab do tabs dikhenge:

| Tab | Kiske liye |
|---|---|
| **`🤖 Auto Analyst`** | Aap batana nahi chahte kya dekhna hai — app khud reports bana de |
| **`📋 Data Table`** | Asli rows dekhni hain — filter karo, pivot banao, CSV nikalo |
| **`🎛️ Manual Dashboard`** | Aapko pata hai kya dekhna hai — khud X aur Y axis chuno |

**Naye ho? `🤖 Auto Analyst` se shuru karo.**

---

## Step 5 — "What this data can show you" table dekho

Auto Analyst kholte hi sabse upar ek table hai. Isme har column ke saamne likha hai
ki app ne usse kya samjha:

| Label | Matlab |
|---|---|
| 📈 **Measure** | Ye number hai — iska total/average nikal sakte hain (Sales, Quantity) |
| 🏷️ **Dimension** | Ye group hai — iske hisaab se data baant sakte hain (Category, Sales Rep) |
| 📅 **Timeline** | Ye date hai — isse trend dekh sakte hain |
| 🌍 **Geography** | Ye jagah hai — map par dikha sakte hain (City, State, Country) |
| 🔑 **Identifier** | Ye har row ka unique naam/number hai — chart me kaam ka nahi |
| 🔘 **Flag** | Sirf do value wali cheez (Yes/No, Paid/Unpaid) |

**Original name** column me aapka asli header hai, aur **Column (as shown)** me wo
naam jo app charts me dikhayega (`TaxAmount` → `Tax Amount`).

---

# Part 2 — 🤖 Auto Analyst ka poora guide

Table ke neeche likha hoga: **`📑 8 ready-made reports from your sheet`**

Har tab ek sawaal ka jawaab hai. Kisi bhi tab par click karke kholo.

## Har report me aapko teen cheezein milengi

1. **❓ Sawaal** — sabse upar, mote akshar me. Ye report kya batayegi.
2. **📖 How to read this** — har chart ke neeche. Chart ko padhna kaise hai.
3. **💡 What it means** — hare box me. Aapke data se nikla asli jawaab.

Sirf **💡 What it means** padh lo to bhi kaam ho jayega.

---

## Report 1 — 📊 Business Overview

**Sawaal:** Business overall kaisa chal raha hai, aur contribute kaun kar raha hai?

Sabse upar bade numbers (KPIs): kitne records, aapke top 3 measures ka total, aur
kitne alag-alag groups hain.

- **Chart 1 (bar)** — kaun sabse zyada laa raha hai. Sabse lamba bar = sabse bada contributor.
- **Chart 2 (donut)** — poora business kaise bata hua hai. Ek slice bahut badi ho to samjho aap us ek naam par tike ho.

> **Yahan se hamesha shuru karo.** 30 second me poori tasveer mil jati hai.

---

## Report 2 — 📈 Growth Over Time

**Sawaal:** Hum badh rahe hain, flat hain, ya gir rahe hain?

Ye tab tabhi aata hai jab aapki sheet me **date column** ho.

- Upar do dropdown: kaunsi date use karni hai, aur kaunsa number track karna hai.
- Line upar ja rahi hai = badh rahe ho. Neeche = gir rahe ho.
- Neeche teen numbers: **Latest period** (pichle period se kitna % upar/neeche),
  **Best period ever**, aur **Typical period**.

App khud decide karta hai daily, weekly ya monthly dikhana hai — aapke data ke
time span ke hisaab se.

---

## Report 3 — 🏆 Top Performers

**Sawaal:** Best kaun hai, aur hum unpar kitne dependent hain?

- **Chart 1** — top 15 ki ranking. Upar wala sabse best.
- **Chart 2 (Pareto)** — ye sabse kaam ka hai. Line dikhati hai ki kitne naam
  milkar 80% business banate hain. Dashed line 80% ka nishan hai.

💡 box me seedha likha aayega jaise: *"Sirf 4 out of 8 Sales Reps 80% Total Amount
banate hain"*. Agar ye number chhota hai, to aapka business kuch hi logon par tika
hai — unhe sambhal kar rakho.

---

## Report 4 — 📉 What Is Normal

**Sawaal:** Normal value kya hai, aur kaunse records galat lagte hain?

- **Chart 1 (histogram)** — sabse lamba bar aapki sabse common value hai.
- **Chart 2 (box)** — box ke bahar door pade dots = ajeeb values.
- Neeche: **Middle value**, **Average**, **Highest**, aur **Unusual values** ki ginti.

> ⚠️ Agar warning aaye ki kuch records normal range se bahar hain, to unhe zaroor
> check karo — ya to wo asli badi deals hain, ya typing mistake. Dono me farak
> aapke saare totals badal deta hai.

---

## Report 5 — 🔗 What Affects What

**Sawaal:** Ek number badalta hai to kaunsa doosra badalta hai?

- **Chart 1 (heatmap)** — row aur column jahan milte hain wahan score dekho.
  **+1 ke paas (laal)** = dono saath badhte hain. **-1 ke paas (neela)** = ek badhta
  hai to doosra girta hai. **0 ke paas** = koi rishta nahi.
- **Chart 2 (scatter)** — har dot ek record. Dots line me upar ja rahe hain to dono
  saath badhte hain.

---

## Report 6 — 🧮 Best Combinations

**Sawaal:** Kaunsa combination best chal raha hai, aur gaps kahan hain?

Do groups ek saath (jaise Sales Rep × Region). Gehra square = zyada business.
Halke/khaali area = wahan aap kaam nahi kar rahe — yahi aapka growth ka mauka hai.

Teen dropdown se aap decide karte ho: side me kya, upar kya, aur andar kaunsa number.

---

## Report 7 — 🌍 Location Map

**Sawaal:** Kaunsi jagah sabse zyada business deti hai?

Map apne aap ban jata hai agar aapke data me City / State / Country ho.
(Details Part 4 me hain.)

---

## Report 8 — 🧪 Can You Trust This Data

**Sawaal:** Kya in charts par bharosa kiya ja sakta hai?

- **How complete** — kitne % cells me actually value hai
- **Repeated rows** — duplicate rows (aapke totals do baar gin rahe hain)
- **Useless columns** — har row me same value, koi matlab nahi
- **Chart** — kis column me kitne gaps hain. 20% se lamba laal bar = risky column

> **Bada faisla lene se pehle ye tab zaroor kholo.**

---

## Multi-sheet: ek se zyada sheet chuni ho to

Har sheet ka **apna alag section** milega:

```
📄 sales_data   📄 Purchase_data   📄 Company Data   ⚖️ Auto Compare
```

Har sheet ke andar wahi 8 reports honge, **sirf us sheet ke data par**.

> **Sheets jodi kyun nahi jatin?** Kyunki alag sheets ke columns alag hote hain.
> Jodne par table zyadatar khaali ho jata hai aur totals galat aate hain.

### ⚖️ Auto Compare (sabse aakhri tab)

- **Chart 1** — kaunsi sheet sabse badi hai
- **Chart 2** — har sheet ka headline number (har sheet ka apna main number)
- **Shared columns** — kaunse columns saari sheets me common hain
- **Chart 3** — wahi common numbers, sheet by sheet
- **Chart 4** — wahi breakdown har sheet me, aur sabse bada gap kahan hai

Agar sheets me kuch bhi common na ho, tab bhi size aur headline numbers compare ho jate hain.

---

# Part 2b — 📋 Data Table

Jab charts nahi, **asli rows** dekhni hon.

## Filters

**`🔍 Filters`** kholo:

- **`Search all columns`** — kuch bhi type karo (order number, city, naam) — poori table me dhoondhega
- **`Filter on specific columns`** — jis column par filter chahiye wo chuno. App khud sahi control deta hai:
  - Number column → **slider** (range)
  - Date column → **date range picker**
  - Text column → **checklist** (values chuno)

## Pivot table

**`🔀 Show as pivot table`** par tick karo. Char controls aayenge:

| Control | Kya |
|---|---|
| **Rows** | Side me kya (Region, Category…) |
| **Columns** | Upar kya (optional) |
| **Values** | Kaunsa number (ya "count of rows") |
| **Summarise by** | Sum / Average / Count / Highest / Lowest |

Row aur column dono ke **Total** apne aap aa jate hain — bilkul Excel pivot jaisa.

## Table ka size

- **`Table height`** slider — table itni hi lambi rahegi, andar scroll hoga. Isse filters upar hi dikhte rehte hain
- **`Columns to show`** — jo columns nahi chahiye hata do; baaki side me scroll ho jayenge
- **`⬇️ Download CSV`** — jo abhi screen par dikh raha hai wahi download hoga (filter/pivot ke saath)

---

# Part 3 — 🎛️ Manual Dashboard ka poora guide

Jab aapko **pata hai** kya dekhna hai, tab ye use karo.

## Upar ke 4 numbers

| Number | Matlab |
|---|---|
| **📊 Total Records** | Kitni rows par charts bane hain |
| **📋 Total Columns** | Kitne columns hain |
| **⚠️ Missing Data (Nulls)** | Kitne cells khaali hain |
| **✨ Unique Categories** | Pehle column me kitni alag values hain |

## Slicers — yahi asli control hai

**`### 🎛️ Dashboard Slicers (Customize Your View)`** ke neeche do dropdown:

1. **`Select Dimension (X-Axis)`** — *kis hisaab se* baantna hai
   (Sales Rep, Category, City…)
2. **`Select Metric (Y-Axis)`** — *kya* naapna hai
   - `Count (Frequency)` = kitni rows
   - koi number column = us column ka total

**Sochne ka tarika:** "Mujhe **[Metric]** dekhna hai **[Dimension]** ke hisaab se."
Jaise — "Total Amount dekhna hai City ke hisaab se."

Dono dropdown badalte hi neeche ke dono charts **aur map** turant badal jate hain.

## Do charts

- **Bar chart** — comparison ke liye. Kaun aage, kaun peeche.
- **Pie/Donut chart** — share ke liye. Kiska kitna hissa.

## Multi-sheet me Manual Dashboard

- **`📄 Sheet Dashboards`** — har sheet ka apna tab
- **`⚖️ Master Comparison`** — checkbox **`📊 Compare all N selected sheets`** on karo,
  phir Dimension me **`Source_Sheet`** chuno. Ab ek hi chart me saari sheets compare ho jayengi.

---

# Part 4 — 🌍 Maps ka guide

**`### 🌍 Geographical Intelligence`** apne aap aata hai jab data me jagah ho.

**`Map Style`** me teen options (jo aapke data ke hisaab se dikhte hain):

### 🗺️ Region Map
Poore ilaake rang jate hain. Gehra rang = zyada business.
Ye work karta hai: **Country** (India, IND, IN — teeno ek hi mane jayenge),
**Indian States** (Maharashtra, ya sirf `MH`), **Indian Districts**, **US States**.

> 🇮🇳 India ke map me **Jammu & Kashmir aur Ladakh dono** included hain.

### 📍 Pin Map (Blinking)
Har city par blink karta hua pin. Pin par mouse le jao to exact value dikhegi.
Scroll karke zoom, drag karke pan.
City ke naam kaafi hain — latitude/longitude ki zarurat nahi.
`BOM`, `BLR`, `CCU` jaise airport codes bhi chalte hain, aur `Bangalore`/`Gurgaon`
jaise purane naam bhi.

### 🧩 Treemap Drill-Down
Blocks me Country ➡️ State ➡️ City. Kisi block par click karke andar jao.
Jab map nahi ban sakta, ye hamesha kaam karta hai.

### Map ke controls

| Control | Options |
|---|---|
| **`Zoom`** | `🎯 Auto Fit` (data par zoom) / `🌍 Whole World` (poori duniya) |
| **`Projection`** | `🗺️ Flat Map` / `🔮 3D Globe` (ghumane wala globe) |
| **`✨ Blink pins`** | Pin blink on/off |

> 💡 India ka data hai to **`🎯 Auto Fit`** best lagta hai.

---

# Part 5 — 🧠 AI features

Ye tabhi chalenge jab sidebar me **`API Connected! ✅`** dikh raha ho.

## 1. AI Analyst Briefing

Auto Analyst ke neeche **`✨ Ask the AI what to look at`** button. Dabane par AI batayega:

1. Ye data actually hai kya
2. Sabse pehle kya 3 cheezein dekhni chahiye
3. Data me kya risk hai
4. Ye data kaunse business sawaalon ka jawaab de sakta hai
5. Kaunsa column add karne se sabse zyada fayda hoga

> 🔒 **Privacy:** AI ko sirf column ke *statistics* jate hain — aapki asli rows kabhi nahi.

## 2. AI Micro-Level Deep Dive

Page ke neeche. **`Select Target Column for Deep Dive:`** me koi ek column chuno,
phir **`🔍 Run Micro-Analysis`**. AI us ek column par patterns, anomalies,
business impact aur recommendation dega.

## 3. Custom Chat

Sabse neeche. Apni bhasha me kuch bhi poocho, jaise:
*"Which city should we focus on next quarter?"*

---

# Part 6 — Sidebar settings

| Setting | Kaam |
|---|---|
| **`⚙️ AI Settings`** → **`Select AI Engine`** | Kaunsa Gemini model use karna hai |
| **`🧹 Which rows count?`** | Row rules (Part 1, Step 3 dekho) |

---

# Problem aaye to

| Problem | Solution |
|---|---|
| Chart khaali dikh raha hai | Us column me shayad values hi nahi. `🧪 Can You Trust This Data` tab kholo aur missing % dekho |
| Map nahi ban raha | App batayega kyun. City-level map ke liye `Latitude`/`Longitude` columns add karo, ya `🧩 Treemap Drill-Down` use karo |
| Google Sheet nahi khul rahi | App exact wajah aur solution batata hai — private sheet ke liye service account wala rasta apnao |
| AI kaam nahi kar raha | Sidebar me `API Connected! ✅` check karo. `.env` file me `GEMINI_API_KEY` hona chahiye |
| Verification code nahi aaya | Spam folder dekho. Phir bhi nahi to `Resend code` dabao (60 second baad) |
| Login nahi ho raha | 5 galat koshishon ke baad 15 minute ka lock lagta hai — wait karo |
| Rows kam dikh rahe hain | Cleaning report kholo — wahan likha hai kaunsi rows kyun hati. Sidebar ke switches se badal sakte ho |
| Total galat lag raha hai | `🧪 Can You Trust This Data` me duplicate rows check karo |

---

# Cheat Sheet

| Aapko chahiye | Kahan jao |
|---|---|
| Jaldi se poori tasveer | `🤖 Auto Analyst` → `📊 Business Overview` |
| Badh rahe hain ya nahi | `📈 Growth Over Time` |
| Best performer kaun | `🏆 Top Performers` |
| Galat records dhoondhna | `📉 What Is Normal` |
| Data par bharosa karna hai ya nahi | `🧪 Can You Trust This Data` |
| Sheets compare karni hain | `⚖️ Auto Compare` |
| Apni marzi ka chart | `🎛️ Manual Dashboard` → Slicers |
| Map par dekhna | `🌍 Geographical Intelligence` |
| AI se salah | `✨ Ask the AI what to look at` |
| Account se nikalna | Sidebar → `Log out` |

---

**Ek line me:** File do → cleaning report par nazar daalo → `🤖 Auto Analyst` kholo →
har report me **💡 What it means** padho. Bas.
