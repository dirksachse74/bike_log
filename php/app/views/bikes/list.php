<div class="actions"><a class="btn primary" href="<?= h(url('bike_edit')) ?>">+ Add bike</a></div>
<?php if (!$bikes): ?><p class="muted">No bikes yet.</p><?php endif; ?>
<table class="list">
  <thead><tr><th>Bike</th><th>Status</th><th class="num">Km</th><th class="num">Rides</th></tr></thead>
  <?php foreach ($bikes as $b): ?>
  <tr><td><a href="<?= h(url('bike', ['id' => $b['id']])) ?>"><?= h($b['name']) ?></a> <span class="muted"><?= h(trim($b['maker'] . ' ' . $b['model'])) ?></span></td>
    <td><?= status_badge($b['status']) ?></td><td class="num"><?= h(km((float)$b['stats']['km'])) ?></td><td class="num"><?= (int)$b['stats']['rides'] ?></td></tr>
  <?php endforeach; ?>
</table>
