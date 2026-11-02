<p class="muted">Several chains taking turns on one bike: one rides, the others are waxed and ready or waiting for wax.</p>
<ul><?php foreach ($bikes as $b): ?><li><a href="<?= h(url('chains', ['bike' => $b['id']])) ?>"><?= h($b['name']) ?></a></li><?php endforeach; ?></ul>
