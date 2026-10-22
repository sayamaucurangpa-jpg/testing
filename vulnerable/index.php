<?php
// ============================================================
//  LAB ONLY - intentionally vulnerable. NEVER expose this.
//  Bug yang ditanam:
//    - tidak ada validasi ekstensi / MIME
//    - nama file dipakai apa adanya (bisa .php)
//    - file disimpan di dalam webroot dan ikut dieksekusi
// ============================================================

$uploadDir = __DIR__ . '/uploads/';
if (!is_dir($uploadDir)) {
    mkdir($uploadDir, 0777, true);
}

$message = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['file'])) {
    $name = basename($_FILES['file']['name']);          // no sanitising of extension
    $dest = $uploadDir . $name;                          // predictable name
    if (move_uploaded_file($_FILES['file']['tmp_name'], $dest)) {
        $safe = htmlspecialchars($name, ENT_QUOTES);
        $message = 'Uploaded: <a href="uploads/' . $safe . '">uploads/' . $safe . '</a>';
    } else {
        $message = 'Upload failed.';
    }
}
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Vulnerable Upload (lab)</title>
  <style>
    body { font: 15px/1.5 system-ui, sans-serif; max-width: 620px; margin: 60px auto; }
    code { background: #f2f2f2; padding: 1px 4px; border-radius: 3px; }
    .warn { color: #a00; font-weight: 600; }
  </style>
</head>
<body>
  <h1>File Upload <span class="warn">(vulnerable, lab)</span></h1>
  <p>Upload apa saja. Tidak ada pengecekan tipe file.</p>

  <?php if ($message !== ''): ?>
    <p><?= $message ?></p>
  <?php endif; ?>

  <form method="post" enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Upload</button>
  </form>

  <p>File masuk ke <code>uploads/</code> dengan nama aslinya.</p>
</body>
</html>
