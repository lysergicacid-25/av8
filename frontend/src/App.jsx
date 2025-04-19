import React, { useState } from 'react';

function App() {
  const [summary, setSummary] = useState("");
  const [pullSheet, setPullSheet] = useState("");
  const [bom, setBOM] = useState("");
  const [notes, setNotes] = useState("");
  const [filename, setFilename] = useState("");
  const [loading, setLoading] = useState(false);

  const handleUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setFilename(file.name);
    setLoading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("Upload failed");

      const data = await response.json();
      setSummary(data.summary);
      setPullSheet(data.cable_pull_sheet);
      setBOM(data.reflected_bom);
      setNotes(data.notes.join("\n"));
    } catch (error) {
      alert(error.message);
    } finally {
      setLoading(false);
    }
  };

  const downloadFile = (path) => {
    const link = document.createElement('a');
    link.href = path;
    link.download = path.split('/').pop();
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const renderSection = (title, content) => (
    <div style={{ marginTop: '2rem' }}>
      <h2>{title}</h2>
      <div style={{ background: '#f8f8f8', padding: '1rem', borderRadius: '6px', whiteSpace: 'pre-wrap' }}>
        {content || "No data available."}
      </div>
    </div>
  );

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '2rem' }}>
      <h1>AV-GPT Upload</h1>
      <input type="file" onChange={handleUpload} />

      {loading && <p>Processing your file, please wait...</p>}

      {!loading && summary && (
        <>
          {renderSection("System Summary", summary)}
          {renderSection("Cable Pull Sheet", pullSheet)}
          <div style={{ marginTop: '0.5rem' }}>
            <button onClick={() => downloadFile(`/files/${filename}_pullsheet.pdf`)}>Download Pull Sheet PDF</button>{' '}
            <button onClick={() => downloadFile(`/files/${filename}_pullsheet.csv`)}>Download Pull Sheet CSV</button>
          </div>

          {renderSection("Reflected BOM", bom)}
          <div style={{ marginTop: '0.5rem' }}>
            <button onClick={() => downloadFile(`/files/${filename}_bom.pdf`)}>Download BOM PDF</button>{' '}
            <button onClick={() => downloadFile(`/files/${filename}_bom.csv`)}>Download BOM CSV</button>
          </div>

          {renderSection("System Verification Notes", notes)}
          <div style={{ marginTop: '0.5rem' }}>
            <button onClick={() => downloadFile(`/files/${filename}_summary.pdf`)}>Download Summary PDF</button>{' '}
            <button onClick={() => downloadFile(`/files/${filename}_verification.pdf`)}>Download Verification PDF</button>
          </div>
        </>
      )}
    </div>
  );
}

export default App;
