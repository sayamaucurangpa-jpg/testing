<?php
// ============================================================
//  Versi yang sudah dipatch, untuk dibandingkan dengan
//  ../vulnerable/index.php
//  Perbaikan:
//    - cek error upload + ukuran maksimum
//    - whitelist ekstensi
//    - verifikasi isi file dengan finfo (bukan cuma nama)
//    - nama file di-random, ekstensi ditentukan server
//    - disimpan DI LUAR webroot -> tidak pernah dieksekusi
// ============================================================

const MAX_BYTES = 2 * 1024 * 1024;                  // 2 MB
const STORAGE   = __DIR__ . '/../storage/uploads/';

$ALLOWED = [
    'image/png'  => 'png',
    'image/jpeg' => 'jpg',
];

$message = '';
$link    = '';

if (!is_dir(STORAGE)) {
    mkdir(STORAGE, 0750, true);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['file'])) {
    $file = $_FILES['file'];

    if ($file['error'] !== UPLOAD_ERR_OK) {
        $message = 'Upload error (code ' . (int)$file['error'] . ').';
    } elseif ($file['size'] > MAX_BYTES) {
        $message = 'File too large.';
    } else {
        $finfo = new finfo(FILEINFO_MIME_TYPE);
        $mime  = $finfo->file($file['tmp_name']);

        if (!isset($ALLOWED[$mime])) {
            $message = 'Only PNG/JPEG images are accepted.';
        } else {
            // nama & ekstensi tidak pernah diambil dari client
            $stored = bin2hex(random_bytes(16)) . '.' . $ALLOWED[$mime];
            $dest   = STORAGE . $stored;

            if (move_uploaded_file($file['tmp_name'], $dest)) {
                chmod($dest, 0640);
                $message = 'Upload OK.';
                $link    = 'download.php?f=' . urlencode($stored);
            } else {
                $message = 'Could not store file.';
            }
        }
    }
}
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Secure Upload</title>
  <style>
    body { font: 15px/1.5 system-ui, sans-serif; max-width: 620px; margin: 60px auto; }
  </style>
</head>
<body>
  <h1>File Upload (patched)</h1>

  <?php if ($message !== ''): ?>
    <p><?= htmlspecialchars($message, ENT_QUOTES) ?></p>
  <?php endif; ?>

  <?php if ($link !== ''): ?>
    <p><a href="<?= htmlspecialchars($link, ENT_QUOTES) ?>">Lihat file</a></p>
  <?php endif; ?>

  <form method="post" enctype="multipart/form-data">
    <input type="file" name="file" accept="image/png,image/jpeg" required>
    <button type="submit">Upload</button>
  </form>

  <p>Disimpan di <code>../storage/uploads/</code>, di luar document root.</p>
</body>
</html>
