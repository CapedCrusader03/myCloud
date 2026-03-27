This is my cloud storage project. Hoping to build a full fledged cloud storage system with features like file upload, download, sharing, and more. 

I am using the following technologies:
- Frontend: React
- Backend: Python, FastAPI 
- Database: Postgres
- Storage: Postgres, could be changed to AWS S3 in future
- Authentication: JWT
- Deployment: Docker, Kubernetes


Right now, I am using polling to check the status of the upload. I will be using SSE to notify the frontend when the upload is complete for a better user experience. 
