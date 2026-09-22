# Personal Secretary

Personal AI assistant built in Python to bring together email, calendar information and personal organisation in one application.

I started this project to explore how software could reduce the amount of routine administration I deal with as a student. Rather than building a simple chatbot, I wanted to work with real data and real services, while keeping the system under my control.

The project is still under active development.

## What it does

### Email

The assistant connects to Gmail and analyses incoming messages using the Claude API.

It can currently:

- Identify emails that require action
- Categorise emails and assign priorities
- Produce short summaries of messages
- Identify when a reply is needed
- Generate editable reply drafts
- Detect tutoring enquiries and requested availability
- Store analysed emails locally so they do not need to be repeatedly processed

The aim is not to replace the inbox. Instead, the assistant turns a large inbox into a smaller list of things that actually need attention.

### Calendar

Google Calendar is integrated into the application so that the assistant can use my schedule when answering questions.

It currently:

- Displays today's events
- Shows upcoming events
- Handles UK timezone information
- Calculates free periods
- Uses calendar availability when dealing with tutoring enquiries

For example, if someone asks about a tutoring lesson on Sunday, the assistant can check my actual calendar rather than relying on a manually maintained list of available times.

### Tutoring

Tutoring is the first example of combining information from multiple sources.

An email enquiry can be analysed to identify the requested day and time. The calendar can then be checked to determine whether that time is available.

This is an early example of the direction I want the project to take: the assistant should understand information from different services and use it together rather than treating each integration independently.

### Web interface

The application uses Streamlit to provide a single interface for the different parts of the assistant.

Current sections include:

- Dashboard
- AI Assistant
- Email
- Tutoring
- Calendar
- Finance
- Health
- University
- Settings

Some of these sections are currently placeholders for future development.

## Technical implementation

The project is written in Python and currently uses:

- Python
- Streamlit
- Anthropic Claude API
- Gmail API
- Google Calendar API
- SQLite
- Google OAuth 2.0
- Git and GitHub

The application is split into separate services rather than putting all of the functionality into one file.

Personal-Secretary/
│
├── ai/
│   └── claude.py
│
├── database/
│   └── database.py
│
├── services/
│   ├── gmail.py
│   └── calendar.py
│
├── app.py
├── requirements.txt
└── README.md