<div class="card">
  <p><?= h($text) ?></p>
  <?php if (!empty($link)): ?><p><a class="btn primary" href="<?= h($link[0]) ?>"><?= h($link[1]) ?></a></p><?php endif; ?>
  <?php if (empty($link) && !Auth::user()): ?><p><a href="<?= h(url('login')) ?>">Sign in</a></p><?php endif; ?>
</div>
