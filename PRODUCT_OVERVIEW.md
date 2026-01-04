VOCIFY - PRODUCT BRIEF
What We're Building
A voice-to-CRM tool that lets sales reps update their CRM by speaking for 30 seconds instead of typing for 10 minutes.

The Problem We Solve
Sales reps waste 5+ hours every week on CRM data entry. After meetings, they either:

Sit in their car typing notes on their phone (painful)
Wait until end of day and try to remember what happened (inaccurate)
Skip it entirely and get yelled at by their manager (common)

This wastes time, creates bad data, and makes reps hate their CRM.

How It Works
Step 1: Rep finishes meeting, walks to car, opens app, hits record
Step 2: Rep speaks naturally for 30 seconds:

"Just met Sarah Chen at Acme Corp. She's the VP of Sales. They're interested in our Enterprise plan. Budget is around €50K. Timeline is Q1. She needs to loop in their CFO Mike before deciding. Main concern is integration with their existing Salesforce setup. Competitor they're looking at is DataCo. Next step: Send proposal by Friday and schedule demo for next Tuesday."

Step 3: AI processes the voice memo and extracts:

Contact: Sarah Chen (VP of Sales, Acme Corp)
Deal: €50K, Enterprise plan, expected close Q1
Stakeholders: Sarah (VP Sales), Mike (CFO - not contacted yet)
Objection: Salesforce integration concerns
Competitor: DataCo
Next steps: Send proposal Friday, demo next Tuesday

Step 4: Show rep the extracted data in a clean interface
Step 5: Rep reviews (takes 20 seconds), taps "Approve"
Step 6: CRM automatically updates with all the information
Total time: 60 seconds vs 10 minutes of manual typing

What Makes This Hard

Speech recognition must work in noisy environments (car, street, coffee shop)
AI must understand sales terminology and extract the right data:

Company names vs product names vs people names
Budget vs deal value vs payment terms
Timeline vs next meeting vs deadline
Objections vs questions vs requirements


Must map to correct CRM fields across different CRMs:

HubSpot calls it "Deal"
Salesforce calls it "Opportunity"
Pipedrive calls it "Deal" but structures differently


Must handle edge cases:

Rep misspoke or corrected themselves mid-sentence
Unclear pronouns ("he wants to meet" - who is "he"?)
Multiple deals/contacts mentioned in one memo
Incomplete information (rep forgot to mention budget)


Must be fast (under 60 seconds total, ideally under 30)
Must be accurate enough that reps trust it (85%+ accuracy minimum)


Technical Approach
Voice Capture:

Web-based audio recording (works on mobile browser)
Upload audio file to server

Transcription:

Use Whisper API or Deepgram
Get text transcript in 5-10 seconds

Data Extraction:

Send transcript to Claude/GPT-4 with structured prompt
Prompt asks for JSON output with specific fields:

contacts (array): name, title, company, email, phone
deals (array): value, stage, close_date, product
tasks (array): description, due_date, priority
notes: full meeting summary
competitors: mentioned competitors
objections: concerns raised


Parse JSON response

Field Mapping:

Map our standard fields to each CRM's specific fields
HubSpot: use their REST API to update Deal, Contact, Task objects
Salesforce: use their REST API to update Opportunity, Contact, Task objects
Pipedrive: use their REST API to update Deal, Person, Activity objects

User Review:

Show extracted data in clean UI
Allow inline editing
Highlight low-confidence extractions for review
One-click approve → update CRM


Core Features (MVP)
Must Have (Week 1-2):

Record voice memo (30-120 seconds)
Transcribe with Whisper/Deepgram
Extract structured data with LLM
Connect to HubSpot via OAuth
Show review/approval UI
Update HubSpot when approved
User authentication
Basic error handling

Should Have (Month 1-3):

Support Pipedrive
Support Salesforce
Confidence scoring (auto-approve high confidence)
Multi-language (Spanish, French, German)
Custom field mapping
Usage analytics (how many memos, time saved)

Nice to Have (Later):

Voice commands ("Update deal value to €75K")
Batch processing (multiple memos at once)
Meeting transcription (join Zoom calls)
Mobile apps (iOS, Android)
Team features (shared terminology)


Success Criteria
Product works if:

85%+ extraction accuracy (measured against manual review)
<60 seconds total time (record → review → update)
70%+ of users use it 5+ times per week (daily habit)
70%+ retention after 30 days (people keep using it)

Product fails if:

<75% accuracy (people don't trust it)


2 minutes total time (not faster than typing)


<3 uses per week (not a habit)
<50% retention (people try and quit)


Why This Works Now
Technology is ready:

Whisper API: 95%+ transcription accuracy
GPT-4/Claude: Can reliably extract structured data
Modern browsers: Good audio recording APIs
CRM APIs: Well-documented, stable

Market is ready:

Sales teams hate CRM data entry (validated pain)
Voice AI is mainstream now (everyone uses Siri/Alexa)
Remote/mobile work is normalized
European market is underserved (competitors are US-based)

We can execute:

Technical founder can build it
Sales founder can sell it
Sales founder has network to launch to
Simple enough to ship in 2 weeks


What We're NOT Building
Not building:

❌ Meeting recording/transcription (Gong does this)
❌ Sales coaching (not our focus)
❌ CRM replacement (we integrate with existing)
❌ General voice assistant (CRM-specific only)
❌ AI sales agent (not automating selling, just data entry)

Staying focused:

One job: Make CRM updates fast and easy
One method: Voice memos
One output: Structured CRM data
One target: Sales reps who hate typing


The Business Goal
Short term: Get to €1M ARR in 18 months
How:

€25/month per user
3,500 paying users = €87,500 MRR = €1M ARR
Start with warm network (150 people available Week 1)
Scale through self-serve + manual sales
Expand from Spain to France, Germany, UK

Long term: Either:

Get acquired by HubSpot/Salesforce (€30-50M)
Raise Series A and scale to €10M+ ARR
Stay profitable and small (€5M ARR, high margin)


Design Principles
1. Speed First

Everything should feel instant
No loading spinners unless absolutely necessary
Optimize for mobile (reps are on phones)

2. Trust Through Transparency

Always show what will be updated before updating
Allow editing everything
Explain confidence scores
Clear error messages

3. Simple > Powerful

One voice memo = one CRM update
Don't overload with features
Hide complexity, show simplicity

4. Fail Gracefully

If extraction fails, fall back to showing transcript
If CRM API fails, queue for retry
Never lose user's voice data

5. European-First

GDPR compliant from Day 1
Multi-language from Day 1
EU data storage
Local pricing (€ not $)


That's It
Build a tool that makes CRM updates take 60 seconds instead of 10 minutes. Sales reps will pay €25/month for this. Get 3,500 of them and you have a €1M ARR business.
Everything else is details.
