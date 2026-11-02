<form method="get" class="card">
  <input type="hidden" name="r" value="groupset">
  <p class="muted">Adds every part of a groupset in one step. On a bike, each part goes to its place; taken places are up to you (keep the old part or replace it). The whole step can be undone.</p>
  <label>Groupset
    <select name="tpl" required><?php $o = []; foreach ($templates as $c => $t) { $o[$t['maker']][$c] = $t['name']; } ?><?= options($o, '', true, 'Choose...') ?></select></label>
  <label>Bike
    <select name="bike"><?= options(array_column($bikes, 'name', 'id'), $bikeId ?: '', true, 'No bike: add everything as spares') ?></select></label>
  <button class="btn primary">Next</button>
</form>
<p class="muted">Specs come from templates that are not yet checked against the makers' documentation; check part numbers before you rely on them.</p>
