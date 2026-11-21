# Homework Calendar: setup guide

This guide gets the page working for one student. You do not need to be a programmer. Take it one step at a time. It takes about 30 minutes.

What you are building: a web page that signs in with the student's Google account, reads their Google Classroom (read only, it can never change anything), and saves their checkmarks in a hidden spot in their own Google Drive.

You will need:
- A Google account for yourself (a normal Gmail one is fine).
- The student's school Google email address.
- A free GitHub account (only if you want the page on the internet, Step 4).

Words in **bold** are things you click or type. Google changes its screens now and then. If a name below is not exactly on your screen, look for one that is close.

## 1. See it first (no setup)

You can look at the page with fake homework before you set anything up.

1. Open the page and add `?demo=1` to the end of the address. Example: `.../homework-calendar/?demo=1`.
2. Or open the page and click **Try with sample data**.

Nothing is saved in this mode. It is only to see what the page looks like.

## 2. Set up Google Cloud

Google Cloud is where you tell Google "this app is allowed to ask people to sign in." It is free for this.

### 2a. Make a project

1. Go to <https://console.cloud.google.com/> and sign in with your own Google account.
2. Click the project picker at the top of the page, then **New project**.
3. Name it `Homework Calendar` and click **Create**.
4. Make sure the new project is the one showing at the top of the page.

### 2b. Turn on two services

You need to switch on the **Google Classroom API** and the **Google Drive API**.

1. In the search box at the top, type `Google Classroom API`. Open the result and click **Enable**.
2. Do the same for `Google Drive API`.

### 2c. Set up the sign-in screen

Google calls this area the **Google Auth Platform**. You can find it by searching for `Google Auth Platform` in the top search box. It has pages called **Branding**, **Audience**, **Data Access** and **Clients**.

1. Open **Google Auth Platform**. If you see a **Get started** button, click it.
2. **App name**: type `Homework Calendar`. **User support email**: pick your email.
3. **Audience**: choose **External**.
4. **Contact information**: type your email.
5. Agree to the policy and click **Create**.

Now add the student as an allowed tester. While the app is in testing mode, only people on this list can sign in.

1. Open the **Audience** page.
2. Make sure **Publishing status** says **Testing**. Leave it that way.
3. Under **Test users**, click **Add users**.
4. Type the student's school email and click **Save**.

Then tell Google what the app is allowed to read.

1. Open the **Data Access** page.
2. Click **Add or remove scopes**.
3. Add these five. If you cannot find them in the list, paste each one into the box that says **Manually add scopes**, then click **Add to table** and **Update**:

```
https://www.googleapis.com/auth/classroom.courses.readonly
https://www.googleapis.com/auth/classroom.coursework.me.readonly
https://www.googleapis.com/auth/classroom.announcements.readonly
https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly
https://www.googleapis.com/auth/drive.appdata
```

4. Click **Save**.

The first four only read Classroom. The last one only lets the app use its own hidden file in Drive. It cannot see the student's other Drive files.

### 2d. Make the client ID

The client ID is a long code that names your app. It is not a password. It is fine that it shows in the page.

1. Open the **Clients** page in Google Auth Platform.
2. Click **Create client**.
3. **Application type**: choose **Web application**.
4. **Name**: type `Homework Calendar web`.
5. Under **Authorized JavaScript origins**, click **Add URI** and add the address where the page will live. This is only the start of the address. No slash at the end and nothing after the `.com` or `.io`:
   - For GitHub Pages: `https://<user>.github.io` (put your GitHub name in place of `<user>`)
   - For trying it on your own computer: `http://localhost:8000`
6. Leave **Authorized redirect URIs** empty. This page does not use it.
7. Click **Create**.
8. Copy the **Client ID**. It ends in `.apps.googleusercontent.com`. You do not need the client secret.

Google says changes can take a few minutes, sometimes longer, to start working.

## 3. Paste the client ID into the page

1. Open the file `homework-calendar/config.js` in any text editor (Notepad works).
2. Replace `PASTE-YOUR-CLIENT-ID.apps.googleusercontent.com` with your client ID. Keep the quote marks. It should look like this:

```js
export const CLIENT_ID = '1234567890-abcdefg.apps.googleusercontent.com';
```

3. Save the file.

## 4. Put the page somewhere the student can open it

Pick one.

### Option A: GitHub Pages (the page lives on the internet)

Read this first:
- Free GitHub Pages needs a **public** repository.
- Publishing makes **every file in the repository** visible to anyone who looks. The Homework Calendar page has no secrets in it. The client ID is not a secret. But be sure nothing else in the repository is something you want private.

Steps:
1. Upload your changed `config.js` to the repository on GitHub (or commit and push it).
2. On GitHub, open the repository and click **Settings**.
3. In the left list, click **Pages**.
4. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
5. Under **Branch**, pick your main branch and the `/ (root)` folder, then click **Save**.
6. Wait a minute or two. Refresh the Pages screen until it shows a link.
7. Your page address is:
   `https://<user>.github.io/<repo>/homework-calendar/`
   Replace `<user>` with your GitHub name and `<repo>` with the repository name.
8. Check that Step 2d has `https://<user>.github.io` in the origins list.

### Option B: On your own computer

1. Open a terminal in the `homework-calendar` folder.
2. Type `python3 -m http.server 8000` and press Enter.
3. Open <http://localhost:8000/> in a browser.
4. Check that Step 2d has `http://localhost:8000` in the origins list.

This only works on that computer while the command is running.

## 5. First sign-in

1. Open the page and click **Sign in with Google**.
2. Choose the student's school account (the one you added as a test user).
3. Google will say **Google hasn't verified this app**. This is normal. Google shows it for every new app that has not been through its review. Click **Advanced**, then **Go to Homework Calendar (unsafe)** (or **Continue**).
4. On the permissions screen, **tick every box**. If you leave one empty, parts of the page will not work.
5. Click **Continue**. The homework should show up.

Note: while the app is in testing mode, Google makes the sign-in expire after about 7 days. The student just clicks **Sign in with Google** again. This is expected.

## 6. If it says the school blocked it

Try it anyway first. Some schools let it through.

If Google shows **Access blocked** or the page shows "Your school blocked this app", the school has not allowed the app yet. Google Workspace for Education blocks "unconfigured" outside apps for students under 18 by default. "Unconfigured" means the school has not marked the app as trusted, limited or blocked. The student cannot fix this. The school's IT person has to.

Ask the school's IT person this (you can copy it):

> Please allow a Google app for my child's school account so it can read Google Classroom. In the Admin console, go to Security > Access and data control > API controls > App access control (Manage Third-Party App Access). Choose Configure new app (Add app), search by OAuth App Name or Client ID, and enter this client ID: `<paste your client ID>`. Then set its access to **Trusted** for the student users. The app is read only for Classroom and only uses its own hidden Drive app data. It does not change anything.

Tell them:
- It can take up to 24 hours for the change to start working, though it is often faster.
- Some schools have a request form. Students may see a button to request access.

If the school says no, there is a fallback. Ask the student to send you their weekly overview Doc instead, and use that to plan the week by hand.

## Using it (for the student)

1. Open the page and click **Sign in with Google**. Use your school account.
2. **What's next** shows the things coming up soonest.
3. **This week** shows Monday to Sunday. Use the arrows to see other weeks. The colors tell you what kind of thing it is: homework, a test, or an activity. Tests stand out so you can plan ahead.
4. **Checklist** lists the things to do. Tick a box when it is done. Your ticks are saved, so they are there next time.
5. Click **+ Add** to add something of your own. Pick **Activity**, **Test** or **Other homework**, give it a name and a date. Add a time if you like. Tick **Every week** for things like practice.
6. Sometimes Classroom has a test but no date. Under **What's next** the page shows an **Add a date** section with an **Add date** button. Click it and pick the date so the test shows in the right place.
7. Click **Refresh** to load new things from Classroom.
8. If the page says "Showing saved info, can't reach Google right now.", you are offline. Your saved things still show. Try Refresh later.
