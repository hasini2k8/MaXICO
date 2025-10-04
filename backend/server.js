const express = require("express");
const multer = require("multer");
const cors = require("cors");
const path = require("path");
const fs = require("fs");

// Create uploads folder if it doesn't exist
const uploadsDir = path.join(__dirname, "uploads");
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir);
}

const app = express();
const PORT = 5000;

// Enable CORS
app.use(cors());

// Parse JSON bodies
app.use(express.json());

// Configure multer storage
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, uploadsDir),
  filename: (req, file, cb) => cb(null, file.originalname),
});

const upload = multer({ storage });

// Upload endpoint
app.post("/api/upload", upload.single("video"), (req, res) => {
  try {
    const summary = JSON.parse(req.body.summary || "{}");
    console.log("Received video:", req.file);
    console.log("Received summary:", summary);

    res.json({ message: "Upload successful!" });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Upload failed" });
  }
});

app.get('/', (req, res) => {
  res.send('Server is running! Use POST /api/upload to upload videos.');
});

// Start server
app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));
