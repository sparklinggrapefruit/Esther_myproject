# Systematic Review Helper

The **Systematic Review Helper** is a small Windows desktop app that helps you screen articles for a systematic review. You give it:

- An EndNote / ProQuest-style **tagged `.txt` export** of your articles, and  
- A **research theme or question** in plain language,

and the app will:

- Parse the export into a table of articles,  
- Send each title + abstract to an OpenAI model,  
- Assign a **1–10 relevance score** to each article based on your theme, and  
- Let you **export a scored CSV** for further analysis.

This README is written for **end users** who will run the app via the `SysReviewHelper.exe` file. If you want to modify the code or work with the Python source directly, please see the separate **Developer’s Guide** in `doc/developer_guide.md`.

---

## 1. What You Need

To use this app, you will need:

1. A **Windows computer** (tested on Windows 10/11).  
2. An **OpenAI account** and a valid **OpenAI API key**.  
3. An **Clarivate Endnote`.txt` export** of your articles.  
4. The `SysReviewHelper.exe` file (included in this repository).

You do **not** need to install Python or any other development tools if you are only using the `.exe`.

---

## 2. Getting Your OpenAI API Key

Before running the app, you must have an OpenAI API key.

1. Log in to your **OpenAI** account.  
2. Go to the page where you can create **API keys**.  
3. Click **“Create new secret key”**.  
4. Copy the key (it will look like `sk-...`).  
5. Keep this key somewhere safe. You will paste it into the app the first time you run it.

You are responsible for any **API costs** associated with your use of this tool. The app simply uses your key; it does not manage your billing or enforce usage limits.

---

## 3. Getting and Starting the App

### 3.1 Locating `SysReviewHelper.exe`

1. Download this project (for example, from GitHub as a ZIP) and extract it, **or** use the provided ZIP that already contains the built executable.  
2. Inside the extracted folder, look for:

   ```text
   dist/SysReviewHelper.exe
(or wherever your instructions say the .exe is located).
3. You can move SysReviewHelper.exe to any folder you like (e.g., your Desktop or a “Tools” folder).

### 3.2 First-Time Run and API Key Prompt

1. Double-click SysReviewHelper.exe to start the app.
2. Windows may show a warning such as “Windows protected your PC” because the app is unsigned. If you trust the source:
3. Click “More info”.
4. Click “Run anyway”.
5. On first run, a small popup will appear asking for your OpenAI API key.
6. Paste your API key into the box and click OK.
7. The app saves your key locally on your computer so you do not need to enter it again.
8. If you ever want to reset this key, see the troubleshooting section below.
9. After you enter the key, the main app window will open.

-----
# 4. Before Using the App

### 4.1 Preparing Your Input File
The app expects a tagged text export from EndNote / ProQuest that looks roughly like this:
%0 Journal Article
%A Smith, John
%A Doe, Jane
%T Example article title
%D 2023
%R https://doi.org/...
%X First line of abstract...
Second line of abstract...
%0 Journal Article
...
Important tags:
- %0 – start of a new record
- %A – author (can appear multiple times)
- %T – title
- %D – year / date
- %R – DOI or URL
- %X – start of the abstract, which may continue on following lines until the next line starting with %

If your export uses a different format (for example RIS, BibTeX, or plain CSV), the app may not parse it correctly. In that case, re-export your results from your database or reference manager using a tagged text / EndNote-style format that includes these % tags. 

Pro tip: USE EndNote Clarivate to organize your artiles and export it as txt.
EndNote Clarivate link: https://access.clarivate.com/login?app=endnote

---
# 5. Using the app

### 5.1 Using the app Step by Step
When the main window is open, you will see three main areas:
- Top-left: file upload section
- Top-right: research theme / question box
- Middle / bottom: scoring controls and the table of articles

# Step 1 – Upload Your .txt File
1. Click “Upload EndNote .txt file”.
2. In the file dialog, select your tagged .txt export (for example exportlist.txt).
3. The app will read and parse the file.
- If parsing succeeds:
    - The status label will say something like:
        Parsed 120 articles.
    - The table will fill with your titles, years, and DOIs.
    - The “Run relevance scoring” button will become enabled.
- If parsing fails, you may see:
    - “Failed to parse file” if the file could not be read or understood.
    - “No records found” if the file did not contain any records in the expected format.

# Step 2 – Enter Your Research Theme / Question
1. Go to the box labeled “Research theme / question” (top-right).
2. Type a clear, plain-language description of what your review is about.
    Examples:
    - Interventions that use mobile health apps to increase physical activity in adults.
    - Studies evaluating the effect of sleep tracking wearables on sleep duration and quality.
    - Digital interventions to improve diet quality in adults with type 2 diabetes.
3. This text is what the AI uses to judge how relevant each article is.
4. If you leave this box empty and click “Run relevance scoring”, the app will warn you and ask you to enter a theme.

# Step 3 – Run Relevance Scoring
1. Once your file is parsed and your theme is entered, click “3. Run relevance scoring”.
2. The app will go through each article one by one. For each article, it:
    1. Sends the title, abstract, and your theme to the OpenAI model.
    2. Receives a single number between 1 and 10, where:
        - 10 = extremely strong match to your theme
        - 8–9 = strong match
        - 6–7 = moderate match
        - 4–5 = weak match
        - 2–3 = barely related
        - 1 = unrelated

    3. While scoring is in progress:
        - The status label at the top will say things like:
            Scoring article 5 / 120 ...
        - The “Relevancy (1–10)” column in the table will fill in as each article is scored.
    4. When scoring finishes:
        1. A message box will appear summarizing the result (how many articles were scored and how many, if any, failed).
        2. The DataFrame in the app now includes a relevancy_score column.

    !! For large numbers of articles, this process can take a while. The app currently makes one API request per article and does not have a “Cancel” button.If you wish to terminate the process, just exit the app.

# Step 4 – Export the Scored Results
1. Click “Export scored CSV”.
2. Choose:
    1. A file name (for example parsed_articles_scored.csv), and
    2. A location (such as your Documents folder).
3. Click Save.
4. The exported CSV will contain:
    - Authors
    - Title
    - Abstract
    - Year
    - DOI
    - relevancy_score (1–10)
You can open this CSV in Excel, R, Python, or any other tool to sort, filter, and continue your screening process.

--- 

## 6. Troubleshooting & Common Issues

### 6.1 The App Keeps Asking for an API Key
On first run, the app asks for your OpenAI API key and saves it locally so you do not need to enter it again. If you keep seeing the key prompt:
    1. Make sure you clicked OK after pasting your key.
    2. Check that your key is still valid in your OpenAI account (for example, it has not been deleted or expired).
If you want to reset the saved key:
    1. Close the app.
    2. Go to your home folder (for example C:\Users\<YourName>).
    3. Delete the file: ".sysreview_config.json"
    4. Run SysReviewHelper.exe again.
    5. When prompted, enter your new API key.

### 6.2 “Failed to Parse File” or “No Records Found”
If you see an error when uploading your .txt file:
1. Confirm that you exported a tagged text / EndNote-style .txt file.
2. Open the file in a text editor and check for lines that start with:
    %A, %T, %D, %R, %X, and %0.
3. Ensure the file:
    - Is not empty, and
    - Actually contains records with these tags.
4. If the file looks more like RIS (TY - JOUR, etc.) or BibTeX (@article{...}), re-export from your reference manager using a tagged format instead.

### 6.3 The App Seems Slow or “Frozen” During Scoring
For many articles (e.g., hundreds), this will take a noticeable amount of time, and The window may feel less responsive while scoring is in progress... 
1. So just be patient.
2. Make sure your internet is working
3. Check your rate limits or quota from OpenAI 

### 6.4 Scoring Does not Look Right
If the scoring looks off, try re-writing your theme to be more specific and clear. 
Reminder that this tool is meant to help you prioritize and triage articles, not replace your judgement. 

---

## 7. Known Limitations
1. The app currently supports only tagged .txt exports with the specific % tags described above. Other formats (RIS, BibTeX, etc.) are not supported.
2. The scoring is AI-based and may sometimes misjudge relevance. Use it as a helper, not a final decision-maker. Be conservative about the scoring cut-off that you want to include/exclude in your final review.
3. Your OpenAI API key is stored unencrypted in a small configuration file on your computer. Do not share this file; treat it like a password.
4. The app does not perform deduplication of articles (for example, it does not detect duplicate DOIs automatically).
For more technical limitations, design decisions, and ideas for future work, see the Developer’s Guide.

---

# 8. Acknowledgements
This app is built using:
1. OpenAI's Python library for relevance scoring
2. pandas for data handling
3. Python's built-in Tkinter for the GUI
And thank you to Dr. Chris Harding for all the feedbacks and improvements to help shape this tool

---

# 9. User's Acknowledgements
Feel free to distribute, share or use this tool as needed for class, personal projects or papers, but please do so with acknowledgements to the developer. If you use this tool for your systematic review project, please acknowledge this tool "SysReviewHelper" and my name "Hyun Seon (Esther), Kim" in your paper or project reports. 