# Input: Firebase deletion

Synthetic authorized code/configuration excerpt: account deletion calls Firebase Auth delete. Firestore documents `users/{uid}` have a TTL timestamp. A separate collection `users/{uid}/messages/{message}` and Storage paths `uploads/{uid}/...` contain test data. The only provided deletion code invokes Auth delete; no deletion workflow, extension settings, backup schedule or deployed configuration is provided. Client config contains a Firebase API key placeholder.
