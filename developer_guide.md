## Developer's guide

This document is written for a developer who is taking over the Systematic Review Helper project. It explains what the project does, how it is structured, how to run and deploy it, how the code flows when a user interacts with it, and what limitations and future directions you should be aware of.

The Systematic Review Helper is a Python-based desktop application that assists researchers with screening article titles and abstracts for systematic reviews. The core idea is simple: the app reads a tagged .txt export from a reference manager (e.g., EndNote/ProQuest), parses it into a structured table of articles, allows the user to specify any systematic review theme or research question in free text, and then uses the OpenAI API to assign a 1–10 relevance score to each article based on that theme. The app provides a Tkinter-based GUI for non-technical users and a separate command-line pipeline for batch processing.

From the beginning, the design goals were: (1) make it easy for researchers to screen large numbers of abstracts; (2) avoid hard-coding to one specific topic (so the tool can adapt to any research theme); and (3) allow users to use their own OpenAI API keys without sending those keys to a third-party server. The current implementation achieves these goals in a minimal but usable way.

Overview and Implemented Specification

At a high level, the project consists of a few main Python modules:

gui.py provides the Tkinter desktop application. It handles user interaction: loading files, entering a theme, running relevance scoring, and exporting results.

parser.py provides a command-line parser for tagged .txt files and writes the parsed data to a CSV file.

chatgpt_helper.py provides an asynchronous batch scoring pipeline that reads a CSV of parsed articles and writes out a CSV with relevance scores.

config_loader.py handles the acquisition and storage of the user’s OpenAI API key in a simple local configuration file.

app.py contains an older/alternate parsing script; it is not used by the main GUI but is left in the repo as a reference.

The data/ folder is used for storing parsed and scored CSVs.

The final system implements the following planning specifications:

It supports EndNote/ProQuest-style tagged .txt exports that use tags such as %0 (start of record), %A (author), %T (title), %D (year/date), %R (DOI/URL), and %X (abstract). The parser extracts these tags and constructs a pandas.DataFrame with columns like authors, title, abstract, year_published/year published, and doi/DOI.

It provides a graphical interface (built with Tkinter) that allows users to select an input .txt file, view the parsed articles in a table, type in a research theme or question, run relevance scoring via the OpenAI API, and export the scored data to CSV.

The relevance scoring is theme-agnostic. The user’s free-text theme is passed into the prompt, and both the GUI and CLI use a generic rubric that defines 10 as an extremely strong match to the theme and 1 as unrelated. The system no longer hard-codes a particular domain (e.g., physical activity) in the scoring prompt.

The app follows a “bring your own API key” model: users provide their own OpenAI key. That key is stored only on their machine in a JSON file in their home directory, and is then reused on subsequent runs. For command-line tools, the key can also be read from the OPENAI_API_KEY environment variable.

For developers, the project can be packaged into a single Windows executable using PyInstaller, so that non-technical users can simply run SysReviewHelper.exe without installing Python.

Some initial ideas were de-scoped or only partially implemented. For example, the GUI scoring is implemented as a simple blocking loop rather than an asynchronous pipeline, there is no cancel button during scoring, there are no built-in plots or statistics in the GUI, and only the tagged .txt format is supported (no RIS or BibTeX import yet). There is also no dedicated test suite or continuous integration.

Installation, Deployment, and Admin Considerations

The project is written in Python 3 and was developed and tested on Windows. It uses a small set of dependencies: pandas for data handling, openai for interacting with the OpenAI API, and pyinstaller for packaging. Tkinter is used for the GUI and is part of the standard library on most Windows Python installations.

To work on the project from source as a developer, you should create a Python environment and install the required packages. If a requirements.txt file exists, you can use that; otherwise, installing at least openai, pandas, and pyinstaller is sufficient:
pip install openai pandas pyinstaller

From the project root, you can run the GUI directly with:
python gui.py

On first run, gui.py imports config_loader, which calls get_api_key_gui(). This function checks for a configuration file in the user’s home directory (e.g., C:\Users\username\.sysreview_config.json). If the file is not present, it displays a Tkinter dialog asking the user to enter their OpenAI API key. The key is stored in that JSON file in plain text under the "OPENAI_API_KEY" key. On subsequent runs, the app reads the key from the config file and does not prompt again.

The command-line parsing and scoring workflow is separate. You can use parser.py to parse a tagged .txt file into a CSV, and chatgpt_helper.py to score that CSV. For example:
python parser.py data/exportlist.txt -o data/parsed_articles.csv
python chatgpt_helper.py

chatgpt_helper.py uses AsyncOpenAI and calls get_api_key() from config_loader, which checks the OPENAI_API_KEY environment variable first, then the config file, and finally prompts in the console if necessary.

To build a standalone Windows executable for end users, the project uses PyInstaller. From the project root, you can create a single-file, GUI-only executable using:
pyinstaller --onefile --noconsole --name SysReviewHelper --add-data "data;data" gui.py

This command bundles the application and its dependencies into dist/SysReviewHelper.exe. The --noconsole option hides the console window so that only the GUI appears, and --add-data "data;data" includes the data/ directory inside the executable (Windows uses ; as the separator in this argument). A typical distribution flow is to zip dist/SysReviewHelper.exe, share that zip with users, and instruct them to extract it and double-click the .exe. On first run, they will see the API key prompt.

From an admin/security perspective, the app requires outbound HTTPS access to api.openai.com. The OpenAI API key is stored in a plain JSON file in the user’s home directory; this is sufficient for a course project, but might be considered too weak for production scenarios. There are no server-side components: everything runs on the user’s machine except for calls to the OpenAI API.

End-User Interaction and Code Walkthrough

The typical user flow is as follows. The user launches the app. If this is the first time on that machine and no API key is stored, a Tkinter dialog appears asking them to enter their OpenAI API key; once entered, it is stored and reused later. The main window, managed by the SRAppGUI class in gui.py, contains three main areas: a section to upload and display the source file information, a text box where the user can type their research theme or question, and a central area that displays the parsed articles in a table, along with scoring and export buttons.

When the user clicks “Upload EndNote .txt file”, the on_upload_file method of SRAppGUI is triggered. This method opens a file selection dialog via filedialog.askopenfilename, and if the user chooses a file, it passes the path to the parse_endnote_export function defined earlier in gui.py. parse_endnote_export reads the file line-by-line, looks for lines that start with the predefined tags (%0, %A, %T, %D, %R, %X), and builds up a record dictionary for each article. Authors are collected into a list, titles and abstracts are assembled (with %X indicating the start of an abstract and subsequent untagged lines treated as continuation lines), year information is captured from %D, and DOI or URL information is captured from %R. When the parser encounters a new %0 line, it finalizes the previous record and begins a new one. At the end, it returns a pandas.DataFrame with one row per article.

Back in SRAppGUI, on_upload_file assigns this DataFrame to self.df, stores the file path in self.current_file, updates a status label, enables the “Run relevance scoring” button, and calls _populate_table. The _populate_table method clears any existing rows in the Tkinter ttk.Treeview widget and then iterates over self.df, inserting one row per article. For display, the title is truncated if it is very long; the year, DOI, and any existing relevancy score are also shown.

Once the file is loaded, the user can type any research theme or question into the text box (for example, “Effects of mobile health apps on medication adherence in adults with diabetes”). When the user clicks “Run relevance scoring”, the on_run_scoring method is called. This method first checks that self.df exists and is not empty. It then reads the theme text from the tk.Text widget. If the theme is blank, a warning is shown and the scoring is not started. Otherwise, on_run_scoring iterates over each row in the DataFrame, updating a progress label as it goes, and calls score_one_article for each article.

The score_one_article function builds the prompt for the OpenAI model by calling build_messages(theme, title, abstract). This function constructs a “system” message describing the model’s role (“You are an expert researcher assisting with a systematic review...”) and a “user” message that contains: the research theme or question, a generic scoring rubric describing what 10, 8–9, 6–7, 4–5, 2–3, and 1 mean in terms of relevance to that theme, explicit instructions to return only a single integer from 1 to 10, and the article’s title and abstract. This makes the app flexible: the rubric is always framed relative to whatever theme the user typed, so the same code can be used for any topic area.

score_one_article then calls client.chat.completions.create with the chosen model (by default gpt-4o-mini), the messages returned by build_messages, and a temperature of 0 for deterministic behavior. It extracts the model’s textual response from resp.choices[0].message.content and passes that to extract_score. extract_score uses a simple regular expression to search for an integer in the range 1–10 and clamps it between 1 and 10. If no valid integer is found, it returns None. Back in on_run_scoring, each score is appended to a list, the corresponding row in the Treeview is updated with the score (if available), and the loop continues until all articles are scored. At the end, the scores list is assigned to self.df["relevancy_score"], and a final message box informs the user that scoring is complete and how many items, if any, failed to score.

When the user clicks “Export scored CSV”, the on_export_csv method is called. It checks that self.df exists and is not empty, then opens a “Save As” dialog to ask the user where to save the file. The DataFrame is written to CSV using to_csv, including the relevancy_score column. This CSV can then be used for further analysis, filtering, or integration into other tools.

Outside the GUI, the parser.py module provides a more general-purpose parse_exportlist function which performs similar parsing but is designed for command-line usage. It reads a tagged .txt file, builds a DataFrame using a TAGS mapping, writes the result to a CSV (by default data/parsed_articles.csv), and prints a summary. Under its own if __name__ == "__main__": block, it uses argparse to let the user specify input and output paths.

The chatgpt_helper.py module provides an asynchronous scoring pipeline for parsed CSVs, which is more suitable for large numbers of articles. It defines a configuration THEME (now generic rather than hard-coded), uses AsyncOpenAI with the API key obtained from get_api_key, and defines functions build_messages and extract_score that mirror the behavior in gui.py. The main difference is that score_one_async, process_batch_async, and main_async manage asynchronous calls to the OpenAI API, using an asyncio.Semaphore to control concurrency and print out progress and estimated time remaining. The run_scoring function wraps main_async with asyncio.run so that it can be called from the command line. When run directly, chatgpt_helper.py reads data/parsed_articles.csv, scores each article, writes data/parsed_articles_scored.csv, and prints some summary information.

The last important piece is config_loader.py, which centralizes how API keys are read and written. It defines a configuration path in the user’s home directory (~/.sysreview_config.json), private helpers _read_config and _write_config, and two public functions: get_api_key for CLI tools and get_api_key_gui for the GUI. get_api_key tries the environment variable, then the config file, and finally prompts on the console. get_api_key_gui skips environment variables and console prompts, instead using only the config file and a Tkinter dialog. This separation keeps GUI behavior predictable while still allowing convenient environment-based configuration for developers working at the command line.

## Known Issues, Limitations, and Inefficiencies

From a developer’s standpoint, there are several known issues and limitations in the current implementation. None of them are catastrophic for the use case, but they are worth noting if you plan to extend or harden the project.

The main UX limitation is that the GUI scoring loop is blocking and single-threaded. In on_run_scoring, each article is scored sequentially and the call to the OpenAI API is synchronous. For small to moderate datasets, this is acceptable, but for larger datasets (hundreds or thousands of abstracts), the GUI can feel sluggish or temporarily frozen during scoring. There is no cancel or pause button; once scoring begins, the user must wait until it finishes or close the window.

Error handling is also relatively minimal. Parsing errors and scoring errors are handled with generic try/except blocks, with some errors printed to the console (which the user will not see in the packaged .exe) and others displayed in message boxes. Errors related to rate limits, quota, or networking can cause certain articles to receive None as their score; these are counted in the final summary but not otherwise highlighted in the GUI.

The parser assumes a very specific input format with %-prefixed tags. Files that deviate from this format may lead to missing or malformed records; currently, the app only warns the user if no valid records are found, but does not provide detailed feedback on partial parse failures.

From a security perspective, the OpenAI API key is stored in a plain JSON file in the user’s home directory (e.g., .sysreview_config.json). This is convenient and transparent, but it is not encrypted or protected beyond the standard file system permissions. For a classroom or small research context this is usually adequate, but for a more rigorous environment you might want a more robust secrets management approach.

On the performance side, GUI scoring is entirely CPU- and I/O-bound via HTTP requests. For very large datasets, calling OpenAI sequentially via the GUI will be slow; the asynchronous pipeline in chatgpt_helper.py is a better choice in such scenarios, but it is still subject to API rate limits and token usage costs. There is no batching at the API level; each article is currently scored via a separate chat.completions call.

Finally, there is no automated test suite or continuous integration in the current project. Functions like parse_endnote_export and extract_score are reasonably simple, but having unit tests would make future refactoring and format extensions safer.

## Future development
On the UX side, it would be valuable to make scoring non-blocking in the GUI. This could be done by integrating asyncio or threading into gui.py so that API calls run in the background while the Tkinter main loop remains responsive. A progress bar, rather than only a text label, would make long runs more transparent. Adding a “Cancel scoring” button that safely stops the scoring loop would be particularly helpful.

If you plan to continue developing this project, a few structural choices are worth keeping in mind. At the moment, most of the GUI logic and the scoring logic live in gui.py. While this is acceptable for a small project, you may eventually want to move parsing and scoring into a dedicated module (e.g., core.py) and have both the GUI and CLI import from there. This would reduce duplication between gui.py and chatgpt_helper.py and centralize prompt-building and error handling.

config_loader.py is currently the single source of truth for how API keys are stored and retrieved. It is important to keep that centralization: any changes to key management (e.g., encryption, new locations, or OS keychains) should be made there so that both GUI and CLI tools stay in sync.

If you add new features, try to avoid turning SRAppGUI into a “god class” that knows about everything. Instead, prefer adding helper functions or classes for new chunks of logic (e.g., a separate class for plotting or for managing filter/sort state in the table). This will keep the codebase approachable for future developers who read this guide.

Overall.... Systematic Review Helper is a small but functional project: it offers a working end-to-end pipeline from tagged exports to scored abstracts, with a user-friendly GUI and a clear BYOK approach to API keys. The core architecture is simple and understandable, and there is plenty of room for extension in UX, data formats, modeling, security, and testing.