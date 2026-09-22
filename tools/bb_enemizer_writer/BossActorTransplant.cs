using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using SoulsFormats;

// Adds reviewed combat actors and MSB generator events. There is deliberately
// no native ID allocator: every output name and ID is witnessed in the plan.
internal static class BossActorTransplant
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
    };
    internal sealed record Addition(
        string SourceMap, string SourcePart, string SourceAnchorPart, int SourceEntityId,
        Archetype SourceArchetype, string DestinationMap, string DestinationAnchorPart,
        string DestinationPart, int DestinationEntityId,
        string? SourcePartKind = null, string? MaterializeAs = null,
        SourceProvenance? SourceProvenance = null, SourceInitialization? SourceInitialization = null);
    internal sealed record SourceProvenance(string Format, string PartSha256, string AnchorSha256);
    internal sealed record SourceInitialization(int TalkId, int UnkT18, int InitAnimId, int DamageAnimId);
    internal sealed record PrimaryProvenance(string Format, string PartSha256);
    internal sealed record PrimaryInitialization(
        string SourceMap, string SourcePart, int SourceEntityId, Archetype SourceArchetype,
        PrimaryProvenance SourceProvenance, SourceInitialization SourceInitialization,
        string DestinationMap, string DestinationPart, int DestinationEntityId);
    sealed record PrimarySwap(string LogicalKey, List<string> DestinationKeys, Archetype Target, Archetype? UnscaledTarget);
    sealed record PrimaryPlan(string Format, bool DryRun, List<PrimarySwap> Swaps, PrimaryScaling Scaling);
    sealed record PrimaryScaling(bool Enabled, string Mechanism, int ChangeCount, bool Applied, List<PrimaryScale> Changes);
    sealed record PrimaryScale(string LogicalKey, int SourceNpcParamId, int ClonedNpcParamId,
        string SpEffectSlot, int MintedSpEffectId, double HaveSoulRate, int SourceLevel,
        int DestinationLevel, double HpMultiplier, double AttackMultiplier, double DefenseMultiplier);
    sealed record ScalingReport(string Format, bool Applied, string SourcePlanSha256,
        string OutputPlanSha256, string OutputGameparamSha256, List<PrimaryScale> Changes);
    internal sealed record GeneratorAddition(
        string SourceMap, string SourceEvent, int SourceEventId, int SourceEntityId, string SourceFingerprint,
        string DestinationMap, string DestinationEvent, int DestinationEventId, int DestinationEntityId,
        string? DestinationPartName, string? DestinationRegionName,
        Dictionary<string, string> SpawnPartMap, Dictionary<string, string> SpawnPointMap);

    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Bare(string map) => map.EndsWith(".msb.dcx", StringComparison.OrdinalIgnoreCase) ? map[..^8]
        : map.EndsWith(".msb", StringComparison.OrdinalIgnoreCase) ? map[..^4] : map;
    static string Resolve(string root, string map) {
        Need(Path.GetFileName(map) == map && Bare(map).StartsWith("m", StringComparison.Ordinal), "invalid actor map name");
        string bare = Bare(map);
        foreach (string ext in new[] { ".msb.dcx", ".msb" }) { string path = Path.Combine(root, bare + ext); if (File.Exists(path)) return path; }
        throw new FileNotFoundException("no MSBB for actor addition " + map);
    }
    static IEnumerable<MSBB.Part> Parts(MSBB map) => map.Parts.GetEntries();
    static MSBB.Part Part(MSBB map, string name, string role) {
        var rows = Parts(map).Where(p => p.Name == name).ToList();
        Need(rows.Count == 1, $"missing or ambiguous {role} Part {name}"); return rows[0];
    }
    static string Kind(MSBB.Part part) => part switch {
        MSBB.Part.Enemy => "enemy",
        MSBB.Part.DummyEnemy => "dummy_enemy",
        _ => part.GetType().Name,
    };
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static string HashFile(string path) => Hash(File.ReadAllBytes(path));
    static void RequireHash(string? hash, string what) => Need(hash is { Length: 64 }
        && hash.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)), $"invalid {what} SHA256");
    static float[] Values(Vector3 value) => [value.X, value.Y, value.Z];
    static object CanonicalPart(string map, MSBB.Part part) {
        var enemy = part as MSBB.Part.EnemyBase;
        return new {
            format = "bb-boss-actor-pin-v1", map = Bare(map), kind = Kind(part),
            name = part.Name, entity_id = part.EntityID, model_name = part.ModelName,
            description = part.Description, instance_id = part.InstanceID, sib_path = part.SibPath,
            position = Values(part.Position), rotation = Values(part.Rotation), scale = Values(part.Scale),
            draw_groups = part.DrawGroups, disp_groups = part.DispGroups, backread_groups = part.BackreadGroups,
            unk_e04 = part.UnkE04, unk_e05 = part.UnkE05, unk_e06 = part.UnkE06, unk_e07 = part.UnkE07,
            lantern_id = part.LanternID, lod_param_id = part.LodParamID, unk_e0e = part.UnkE0E, unk_e0f = part.UnkE0F,
            enemy = enemy is null ? null : new {
                npc_param_id = enemy.NPCParamID, think_param_id = enemy.ThinkParamID,
                talk_id = enemy.TalkID, chara_init_id = enemy.CharaInitID, unk_t18 = enemy.UnkT18,
                collision_name = enemy.CollisionName, unk_t20 = enemy.UnkT20,
                move_point_names = enemy.MovePointNames, init_anim_id = enemy.InitAnimID, damage_anim_id = enemy.DamageAnimID,
                gparam = new { light_set_id = enemy.Gparam.LightSetID, fog_param_id = enemy.Gparam.FogParamID,
                    light_scattering_id = enemy.Gparam.LightScatteringID, env_map_id = enemy.Gparam.EnvMapID },
            },
        };
    }
    internal static string Fingerprint(string map, MSBB.Part part) =>
        Hash(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(CanonicalPart(map, part), Json)));
    static object CanonicalGenerator(string map, MSBB.Event.Generator item) => new {
        format = "bb-boss-generator-pin-v1", map = Bare(map), name = item.Name,
        event_id = item.EventID, entity_id = item.EntityID, part_name = item.PartName, region_name = item.RegionName,
        unk_e0c = item.UnkE0C, unk_e0d = item.UnkE0D, unk_e0e = item.UnkE0E, unk_e0f = item.UnkE0F,
        max_num = item.MaxNum, gen_type = item.GenType, limit_num = item.LimitNum,
        min_gen_num = item.MinGenNum, max_gen_num = item.MaxGenNum,
        min_interval = item.MinInterval, max_interval = item.MaxInterval,
        initial_spawn_count = item.InitialSpawnCount, unk_t11 = item.UnkT11, unk_t12 = item.UnkT12, unk_t13 = item.UnkT13,
        spawn_part_names = item.SpawnPartNames, spawn_point_names = item.SpawnPointNames,
    };
    internal static string GeneratorFingerprint(string map, MSBB.Event.Generator item) =>
        Hash(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(CanonicalGenerator(map, item), Json)));
    static void RequireArchetype(MSBB.Part.EnemyBase part, Addition add) => Need(part.EntityID == add.SourceEntityId
        && part.ModelName == add.SourceArchetype.ModelName && part.NPCParamID == add.SourceArchetype.NpcParamId
        && part.ThinkParamID == add.SourceArchetype.ThinkParamId && part.CharaInitID == add.SourceArchetype.CharaInitId,
        $"{add.SourceMap}:{add.SourcePart}: donor provenance drift");
    static void RequireUnique(IEnumerable<Addition> additions) {
        Need(additions.Select(a => (Bare(a.DestinationMap), a.DestinationPart)).Distinct().Count() == additions.Count(), "duplicate actor destination Part");
        Need(additions.Select(a => (Bare(a.DestinationMap), a.DestinationEntityId)).Distinct().Count() == additions.Count(), "duplicate actor destination entity ID");
    }
    static void RequireUniqueGenerators(IEnumerable<GeneratorAddition> additions) {
        Need(additions.Select(a => (Bare(a.DestinationMap), a.DestinationEvent)).Distinct().Count() == additions.Count(), "duplicate generator destination event name");
        Need(additions.Select(a => (Bare(a.DestinationMap), a.DestinationEventId)).Distinct().Count() == additions.Count(), "duplicate generator destination event ID");
        Need(additions.Select(a => (Bare(a.DestinationMap), a.DestinationEntityId)).Distinct().Count() == additions.Count(), "duplicate generator destination entity ID");
    }
    static Vector3 Rotate(Vector3 offset, float yaw) => Vector3.TransformNormal(offset, Matrix4x4.CreateRotationY(yaw));

    internal static List<Addition> Read(string planPath, bool required) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_actor_additions", out var node)) {
            Need(!required, "missing boss_actor_additions"); return [];
        }
        var additions = node.Deserialize<List<Addition>>(Json) ?? throw new InvalidDataException("invalid boss_actor_additions");
        Need(additions.Count > 0, "boss_actor_additions must not be empty"); RequireUnique(additions); return additions;
    }
    internal static List<GeneratorAddition> ReadGenerators(string planPath, bool required) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_generator_additions", out var node)) {
            Need(!required, "missing boss_generator_additions"); return [];
        }
        var additions = node.Deserialize<List<GeneratorAddition>>(Json) ?? throw new InvalidDataException("invalid boss_generator_additions");
        Need(additions.Count > 0, "boss_generator_additions must not be empty"); RequireUniqueGenerators(additions); return additions;
    }
    internal static List<PrimaryInitialization> ReadPrimaryInitializations(string planPath, bool required) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_actor_initializations", out var node)) {
            Need(!required, "missing boss_actor_initializations"); return [];
        }
        var initializations = node.Deserialize<List<PrimaryInitialization>>(Json)
            ?? throw new InvalidDataException("invalid boss_actor_initializations");
        Need(initializations.Count > 0, "boss_actor_initializations must not be empty");
        Need(initializations.Select(item => (Bare(item.DestinationMap), item.DestinationPart)).Distinct().Count() == initializations.Count,
            "duplicate primary actor initialization destination Part");
        Need(initializations.Select(item => (Bare(item.DestinationMap), item.DestinationEntityId)).Distinct().Count() == initializations.Count,
            "duplicate primary actor initialization destination entity ID");
        return initializations;
    }
    internal static void ValidatePlan(string planPath, bool required) {
        _ = Read(planPath, required); _ = ReadPrimaryInitializations(planPath, false); _ = ReadGenerators(planPath, false);
    }

    static void RequireProvenance(Addition add, MSBB.Part donor, MSBB.Part anchor) {
        if (add.SourceInitialization is not null)
            Need(add.SourceProvenance is not null, "donor initialization requires source provenance pin");
        if (add.SourceProvenance is null) return; // Compatibility for existing reviewed actor plans.
        var provenance = add.SourceProvenance!;
        Need(provenance.Format == "bb-boss-actor-pin-v1", "unsupported actor provenance format");
        RequireHash(provenance.PartSha256, "actor donor provenance"); RequireHash(provenance.AnchorSha256, "actor anchor provenance");
        Need(provenance.PartSha256 == Fingerprint(add.SourceMap, donor), $"{add.SourceMap}:{add.SourcePart}: donor provenance pin drift");
        Need(provenance.AnchorSha256 == Fingerprint(add.SourceMap, anchor), $"{add.SourceMap}:{add.SourceAnchorPart}: anchor provenance pin drift");
    }
    static void RequireInitialization(Addition add, MSBB.Part.EnemyBase donor) {
        if (add.SourceInitialization is null) return;
        var expected = add.SourceInitialization;
        Need(donor.TalkID == expected.TalkId && donor.UnkT18 == expected.UnkT18
            && donor.InitAnimID == expected.InitAnimId && donor.DamageAnimID == expected.DamageAnimId,
            $"{add.SourceMap}:{add.SourcePart}: donor initialization drift");
    }
    static void ApplyInitialization(Addition add, MSBB.Part.EnemyBase donor, MSBB.Part.Enemy spawned) {
        if (add.SourceInitialization is null) return;
        spawned.TalkID = donor.TalkID; spawned.UnkT18 = donor.UnkT18;
        spawned.InitAnimID = donor.InitAnimID; spawned.DamageAnimID = donor.DamageAnimID;
    }
    static void ApplyActors(List<Addition> additions, string sourceMaps, string destinationMaps, string outputMaps) {
        if (additions.Count == 0) return;
        var sources = new Dictionary<string, MSBB>(StringComparer.Ordinal);
        var targets = new Dictionary<string, (MSBB Map, string Output, HashSet<string> OriginalNames, HashSet<int> OriginalIds, Dictionary<string, PartState> OriginalEnemies)>(StringComparer.Ordinal);
        MSBB Source(string map) { string key = Bare(map); if (!sources.TryGetValue(key, out var value)) sources[key] = value = MSBB.Read(Resolve(sourceMaps, key)); return value; }
        (MSBB Map, string Output, HashSet<string> OriginalNames, HashSet<int> OriginalIds, Dictionary<string, PartState> OriginalEnemies) Target(string map) {
            string key = Bare(map); if (targets.TryGetValue(key, out var value)) return value;
            string original = Resolve(destinationMaps, key), output = Path.Combine(outputMaps, Path.GetFileName(original));
            var loaded = File.Exists(output) ? MSBB.Read(output) : MSBB.Read(original);
            value = (loaded, output, Parts(loaded).Select(p => p.Name).ToHashSet(), Parts(loaded).Select(p => p.EntityID).ToHashSet(),
                Parts(loaded).OfType<MSBB.Part.EnemyBase>().ToDictionary(p => p.Name, PartState.Capture)); targets[key] = value; return value;
        }
        foreach (var add in additions) {
            Need(add.SourceEntityId > 0 && add.DestinationEntityId > 0 && !string.IsNullOrWhiteSpace(add.DestinationPart), "invalid actor identity");
            var donorMap = Source(add.SourceMap);
            var donorPart = Part(donorMap, add.SourcePart, "donor");
            string donorKind = Kind(donorPart);
            if (add.SourcePartKind is not null) Need(add.SourcePartKind == donorKind, "actor source Part kind drift");
            var donor = donorPart as MSBB.Part.EnemyBase;
            Need(donor is not null && donorKind is "enemy" or "dummy_enemy", "actor donor must be an Enemy or explicitly materialized DummyEnemy");
            if (donorKind == "dummy_enemy") {
                Need(add.MaterializeAs == "enemy", "dummy actor donor requires explicit materialize_as enemy");
                Need(add.SourceProvenance is not null, "dummy actor donor requires source provenance pin");
            }
            else Need(add.MaterializeAs is null or "enemy", "unsupported actor materialization");
            RequireArchetype(donor!, add);
            var donorAnchor = Part(donorMap, add.SourceAnchorPart, "donor anchor");
            RequireProvenance(add, donorPart, donorAnchor); RequireInitialization(add, donor!);
            var target = Target(add.DestinationMap);
            var destinationAnchor = Part(target.Map, add.DestinationAnchorPart, "destination anchor") as MSBB.Part.Enemy;
            Need(destinationAnchor != null, "destination actor anchor must be an ordinary Enemy");
            Need(!Parts(target.Map).Any(p => p.Name == add.DestinationPart), "actor destination Part already exists");
            Need(!Parts(target.Map).Any(p => p.EntityID == add.DestinationEntityId), "actor destination entity ID already exists");
            // Clone the destination anchor so its collision, groups, move points,
            // and local loading state stay destination-owned. The plan supplies
            // each imported donor field; it never imports ambient map settings.
            var spawned = (MSBB.Part.Enemy)destinationAnchor!.DeepCopy();
            float yaw = destinationAnchor.Rotation.Y - donorAnchor.Rotation.Y;
            spawned.Name = add.DestinationPart; spawned.EntityID = add.DestinationEntityId;
            spawned.Position = destinationAnchor.Position + Rotate(donor!.Position - donorAnchor.Position, yaw);
            spawned.Rotation = donor.Rotation + new Vector3(0, yaw, 0);
            spawned.ModelName = donor.ModelName; spawned.NPCParamID = donor.NPCParamID;
            spawned.ThinkParamID = donor.ThinkParamID; spawned.CharaInitID = donor.CharaInitID;
            ApplyInitialization(add, donor, spawned);
            if (!target.Map.Models.Enemies.Any(model => model.Name == donor.ModelName)) target.Map.Models.Enemies.Add(new MSBB.Model.Enemy { Name = donor.ModelName, SibPath = "" });
            target.Map.Parts.Enemies.Add(spawned);
        }
        foreach (var (map, output, names, ids, originals) in targets.Values) {
            Directory.CreateDirectory(Path.GetDirectoryName(output)!); map.Write(output);
            var check = MSBB.Read(output);
            Need(names.All(name => Parts(check).Any(p => p.Name == name)) && ids.All(id => Parts(check).Any(p => p.EntityID == id)), "actor round-trip lost an original Part");
            foreach (var (name, state) in originals) {
                var part = Parts(check).OfType<MSBB.Part.EnemyBase>().SingleOrDefault(p => p.Name == name);
                Need(part != null, "actor round-trip lost an original Enemy");
                Need(state.Archetype == new Archetype(part!.ModelName, part.NPCParamID, part.ThinkParamID, part.CharaInitID), "actor round-trip changed an original Enemy archetype");
                state.Invariant.RequireSame(Path.GetFileName(output), part);
            }
        }
    }
    static void ApplyPrimaryInitializations(List<PrimaryInitialization> initializations,
        string planPath, string sourceMaps, string destinationMaps, string outputMaps) {
        if (initializations.Count == 0) return;
        var sources = new Dictionary<string, MSBB>(StringComparer.Ordinal);
        MSBB Source(string map) { string key = Bare(map); if (!sources.TryGetValue(key, out var value)) sources[key] = value = MSBB.Read(Resolve(sourceMaps, key)); return value; }
        foreach (var item in initializations) {
            Need(item.SourceEntityId > 0 && item.DestinationEntityId > 0
                && !string.IsNullOrWhiteSpace(item.SourcePart) && !string.IsNullOrWhiteSpace(item.DestinationPart),
                "invalid primary actor initialization identity");
            var sourcePart = Part(Source(item.SourceMap), item.SourcePart, "primary initialization donor") as MSBB.Part.Enemy;
            Need(sourcePart is not null, "primary initialization donor must be an ordinary Enemy");
            var sourceEnemy = sourcePart!;
            RequireArchetype(sourceEnemy, new Addition(item.SourceMap, item.SourcePart, "", item.SourceEntityId,
                item.SourceArchetype, item.DestinationMap, "", item.DestinationPart, item.DestinationEntityId));
            var provenance = item.SourceProvenance ?? throw new InvalidDataException("primary actor initialization requires source provenance pin");
            var initialization = item.SourceInitialization ?? throw new InvalidDataException("primary actor initialization requires source initialization tuple");
            Need(provenance.Format == "bb-boss-actor-pin-v1", "unsupported primary actor provenance format");
            RequireHash(provenance.PartSha256, "primary actor donor provenance");
            Need(provenance.PartSha256 == Fingerprint(item.SourceMap, sourceEnemy),
                $"{item.SourceMap}:{item.SourcePart}: primary actor donor provenance pin drift");
            RequireInitialization(new Addition(item.SourceMap, item.SourcePart, "", item.SourceEntityId,
                item.SourceArchetype, item.DestinationMap, "", item.DestinationPart, item.DestinationEntityId,
                SourceInitialization: initialization), sourceEnemy);
            string original = Resolve(destinationMaps, item.DestinationMap);
            string output = Path.Combine(outputMaps, Path.GetFileName(original));
            Need(File.Exists(output), "primary actor initialization requires prior map transplant output");
            var map = MSBB.Read(output);
            var target = Part(map, item.DestinationPart, "primary initialization destination") as MSBB.Part.EnemyBase;
            Need(target is not null && target.EntityID == item.DestinationEntityId,
                "primary actor initialization destination provenance drift");
            var targetEnemy = target!;
            var targetArchetype = new Archetype(targetEnemy.ModelName, targetEnemy.NPCParamID,
                targetEnemy.ThinkParamID, targetEnemy.CharaInitID);
            if (targetArchetype != item.SourceArchetype) {
                Need(targetArchetype.ModelName == item.SourceArchetype.ModelName
                    && targetArchetype.ThinkParamId == item.SourceArchetype.ThinkParamId
                    && targetArchetype.CharaInitId == item.SourceArchetype.CharaInitId,
                    "primary actor initialization target does not match source combat archetype");
                RequireReviewedNormalizedClone(planPath, outputMaps, item, targetArchetype.NpcParamId);
            }
            var before = PartInvariant.Capture(targetEnemy);
            targetEnemy.TalkID = sourceEnemy.TalkID; targetEnemy.UnkT18 = sourceEnemy.UnkT18;
            targetEnemy.InitAnimID = sourceEnemy.InitAnimID; targetEnemy.DamageAnimID = sourceEnemy.DamageAnimID;
            map.Write(output);
            var check = MSBB.Read(output);
            var persisted = Part(check, item.DestinationPart, "persisted primary initialization destination") as MSBB.Part.EnemyBase;
            Need(persisted is not null && persisted.TalkID == initialization.TalkId && persisted.UnkT18 == initialization.UnkT18
                && persisted.InitAnimID == initialization.InitAnimId && persisted.DamageAnimID == initialization.DamageAnimId,
                "primary actor initialization round-trip differs from reviewed donor tuple");
            (before with { TalkId = initialization.TalkId, UnkT18 = initialization.UnkT18,
                InitAnimId = initialization.InitAnimId, DamageAnimId = initialization.DamageAnimId })
                .RequireSame(Path.GetFileName(output), persisted!);
        }
    }
    static string OverlayRoot(string outputMaps) {
        var studio = new DirectoryInfo(Path.GetFullPath(outputMaps));
        var map = studio.Parent;
        var dvd = map?.Parent;
        var root = dvd?.Parent;
        Need(studio.Name == "MapStudio" && map?.Name == "map"
            && dvd?.Name == "dvdroot_ps4" && root is not null,
            "scaled primary initialization output layout is invalid");
        return root!.FullName;
    }
    static bool IsPhysicalDestinationKey(string key, PrimaryInitialization item) {
        int separator = key.LastIndexOf(':');
        return separator > 0 && key.IndexOf(':') == separator
            && Bare(key[..separator]) == Bare(item.DestinationMap)
            && key[(separator + 1)..] == item.DestinationPart;
    }
    static void RequireReviewedNormalizedClone(string planPath, string outputMaps,
        PrimaryInitialization item, int actualNpcParamId) {
        string root = OverlayRoot(outputMaps);
        string sourcePlan = Path.Combine(root, "source-enemizer-plan.json");
        string adjustedPlan = Path.Combine(root, "bb-enemizer-plan.json");
        string receiptPath = Path.Combine(root, "scaling-report.json");
        string outputGame = Path.Combine(root, "dvdroot_ps4", "param", "gameparam", "gameparam.parambnd.dcx");
        Need(File.Exists(sourcePlan) && File.Exists(adjustedPlan) && File.Exists(receiptPath) && File.Exists(outputGame),
            "scaled primary initialization requires native scaling evidence");
        Need(File.ReadAllBytes(sourcePlan).SequenceEqual(File.ReadAllBytes(planPath)),
            "scaled primary initialization source plan does not match requested plan");
        var original = JsonSerializer.Deserialize<PrimaryPlan>(File.ReadAllText(planPath), Json)
            ?? throw new InvalidDataException("invalid primary initialization source plan");
        var adjusted = JsonSerializer.Deserialize<PrimaryPlan>(File.ReadAllText(adjustedPlan), Json)
            ?? throw new InvalidDataException("invalid adjusted primary initialization plan");
        var receipt = JsonSerializer.Deserialize<ScalingReport>(File.ReadAllText(receiptPath), Json)
            ?? throw new InvalidDataException("invalid scaling receipt");
        Need(original.Format == "bb-enemizer-plan-v2" && original.DryRun, "invalid primary initialization source plan format");
        Need(adjusted.Format == original.Format && adjusted.DryRun == original.DryRun
            && adjusted.Scaling.Enabled && adjusted.Scaling.Applied
            && adjusted.Scaling.Mechanism == "inferred_static_npc_clone_sp_effect",
            "adjusted plan lacks applied native scaling");
        Need(receipt.Format == "bb-enemizer-scaling-v1" && receipt.Applied
            && receipt.SourcePlanSha256 == HashFile(planPath) && receipt.OutputPlanSha256 == HashFile(adjustedPlan)
            && receipt.OutputGameparamSha256 == HashFile(outputGame),
            "scaled primary initialization receipt does not attest native output");
        var sourceSwaps = original.Swaps.Where(s => s.DestinationKeys.Any(key => IsPhysicalDestinationKey(key, item))).ToList();
        Need(sourceSwaps.Count == 1 && sourceSwaps[0].Target == item.SourceArchetype,
            "primary actor initialization source does not match logical swap");
        var sourceSwap = sourceSwaps[0];
        var adjustedSwaps = adjusted.Swaps.Where(s => s.LogicalKey == sourceSwap.LogicalKey).ToList();
        Need(adjustedSwaps.Count == 1 && adjustedSwaps[0].UnscaledTarget == sourceSwap.Target
            && adjustedSwaps[0].Target.ModelName == sourceSwap.Target.ModelName
            && adjustedSwaps[0].Target.ThinkParamId == sourceSwap.Target.ThinkParamId
            && adjustedSwaps[0].Target.CharaInitId == sourceSwap.Target.CharaInitId
            && adjustedSwaps[0].Target.NpcParamId == actualNpcParamId,
            "primary actor initialization target is not reviewed normalized clone");
        var planChanges = adjusted.Scaling.Changes.Where(change => change.LogicalKey == sourceSwap.LogicalKey).ToList();
        var receiptChanges = receipt.Changes.Where(change => change.LogicalKey == sourceSwap.LogicalKey).ToList();
        Need(planChanges.Count == 1 && receiptChanges.Count == 1
            && planChanges[0] == receiptChanges[0]
            && planChanges[0].SourceNpcParamId == item.SourceArchetype.NpcParamId
            && planChanges[0].ClonedNpcParamId == actualNpcParamId
            && actualNpcParamId is >= 6000000 and <= 6099999,
            "primary actor initialization clone lacks matching native scaling change");
    }
    static MSBB.Event.Generator Generator(MSBB map, string name, int eventId, int entityId, string role) {
        var rows = map.Events.Generators.Where(e => e.Name == name && e.EventID == eventId && e.EntityID == entityId).ToList();
        Need(rows.Count == 1, $"missing or ambiguous {role} generator {name}"); return rows[0];
    }
    static string[] Named(string[] names) => names.Where(name => !string.IsNullOrEmpty(name)).Distinct(StringComparer.Ordinal).Order().ToArray();
    static void RequireMap(Dictionary<string, string>? mapping, string[] source, Func<string, bool> target, string role) {
        Need(mapping is not null && mapping.Count == source.Length && mapping.Keys.ToHashSet(StringComparer.Ordinal).SetEquals(source), $"generator {role} map must cover exactly the source references");
        var actual = mapping!;
        Need(actual.Values.All(value => !string.IsNullOrWhiteSpace(value) && target(value)), $"generator {role} map references a missing destination entry");
        Need(actual.Values.Distinct(StringComparer.Ordinal).Count() == actual.Count, $"generator {role} map aliases destination entries");
    }
    static void SetGeneratorNames(MSBB.Event.Generator generator, string[] parts, string[] points) {
        var type = typeof(MSBB.Event.Generator);
        var partSetter = type.GetProperty(nameof(MSBB.Event.Generator.SpawnPartNames))?.GetSetMethod(true);
        var pointSetter = type.GetProperty(nameof(MSBB.Event.Generator.SpawnPointNames))?.GetSetMethod(true);
        Need(partSetter is not null && pointSetter is not null, "SoulsFormats generator references are not writable");
        partSetter!.Invoke(generator, [parts]); pointSetter!.Invoke(generator, [points]);
    }
    static void ApplyGenerators(List<GeneratorAddition> additions, string sourceMaps, string destinationMaps, string outputMaps) {
        if (additions.Count == 0) return;
        var sources = new Dictionary<string, MSBB>(StringComparer.Ordinal);
        var targets = new Dictionary<string, (MSBB Map, string Output, Dictionary<string, string> Original)>(StringComparer.Ordinal);
        MSBB Source(string map) { string key = Bare(map); if (!sources.TryGetValue(key, out var value)) sources[key] = value = MSBB.Read(Resolve(sourceMaps, key)); return value; }
        (MSBB Map, string Output, Dictionary<string, string> Original) Target(string map) {
            string key = Bare(map); if (targets.TryGetValue(key, out var value)) return value;
            string original = Resolve(destinationMaps, key), output = Path.Combine(outputMaps, Path.GetFileName(original));
            var loaded = File.Exists(output) ? MSBB.Read(output) : MSBB.Read(original);
            Need(loaded.Events.Generators.Select(e => e.Name).Distinct().Count() == loaded.Events.Generators.Count, "ambiguous destination generator name");
            value = (loaded, output, loaded.Events.Generators.ToDictionary(e => e.Name, e => GeneratorFingerprint(key, e))); targets[key] = value; return value;
        }
        var expected = new Dictionary<(string Map, string Name), string>();
        foreach (var add in additions) {
            Need(add.SourceEntityId > 0 && add.DestinationEntityId > 0
                && !string.IsNullOrWhiteSpace(add.SourceEvent) && !string.IsNullOrWhiteSpace(add.DestinationEvent),
                "invalid generator identity");
            RequireHash(add.SourceFingerprint, "generator source");
            var source = Generator(Source(add.SourceMap), add.SourceEvent, add.SourceEventId, add.SourceEntityId, "source");
            Need(add.SourceFingerprint == GeneratorFingerprint(add.SourceMap, source), $"{add.SourceMap}:{add.SourceEvent}: generator provenance pin drift");
            var target = Target(add.DestinationMap);
            Need(!target.Map.Events.GetEntries().Any(e => e.Name == add.DestinationEvent || e.EventID == add.DestinationEventId || e.EntityID == add.DestinationEntityId)
                && !Parts(target.Map).Any(part => part.EntityID == add.DestinationEntityId),
                "generator destination identity already exists");
            RequireMap(add.SpawnPartMap, Named(source.SpawnPartNames), name => Parts(target.Map).Any(p => p.Name == name), "spawn Part");
            RequireMap(add.SpawnPointMap, Named(source.SpawnPointNames), name => target.Map.Regions.Regions.Any(r => r.Name == name), "spawn point");
            string? sourcePart = string.IsNullOrEmpty(source.PartName) ? null : source.PartName;
            string? sourceRegion = string.IsNullOrEmpty(source.RegionName) ? null : source.RegionName;
            Need((sourcePart is null) == string.IsNullOrEmpty(add.DestinationPartName), "generator destination event Part mapping is missing or unexpected");
            Need((sourceRegion is null) == string.IsNullOrEmpty(add.DestinationRegionName), "generator destination event Region mapping is missing or unexpected");
            if (sourcePart is not null) Need(Parts(target.Map).Any(p => p.Name == add.DestinationPartName), "generator destination event Part is missing");
            if (sourceRegion is not null) Need(target.Map.Regions.Regions.Any(r => r.Name == add.DestinationRegionName), "generator destination event Region is missing");
            var clone = (MSBB.Event.Generator)source.DeepCopy();
            clone.Name = add.DestinationEvent; clone.EventID = add.DestinationEventId; clone.EntityID = add.DestinationEntityId;
            clone.PartName = add.DestinationPartName ?? ""; clone.RegionName = add.DestinationRegionName ?? "";
            SetGeneratorNames(clone,
                clone.SpawnPartNames.Select(name => string.IsNullOrEmpty(name) ? name : add.SpawnPartMap[name]).ToArray(),
                clone.SpawnPointNames.Select(name => string.IsNullOrEmpty(name) ? name : add.SpawnPointMap[name]).ToArray());
            target.Map.Events.Generators.Add(clone);
            expected[(Bare(add.DestinationMap), add.DestinationEvent)] = GeneratorFingerprint(Bare(add.DestinationMap), clone);
        }
        foreach (var (map, target) in targets) {
            var (targetMap, output, originals) = target;
            Directory.CreateDirectory(Path.GetDirectoryName(output)!); targetMap.Write(output);
            var check = MSBB.Read(output);
            Need(check.Events.Generators.Select(e => e.Name).Distinct().Count() == check.Events.Generators.Count, "generator round-trip duplicate name");
            foreach (var (name, pin) in originals) {
                var item = check.Events.Generators.SingleOrDefault(e => e.Name == name);
                Need(item is not null && GeneratorFingerprint(map, item) == pin, "generator round-trip changed an original generator");
            }
            foreach (var item in check.Events.Generators.Where(e => expected.ContainsKey((map, e.Name))))
                Need(GeneratorFingerprint(map, item) == expected[(map, item.Name)], "generator round-trip changed a reviewed addition");
            Need(check.Events.Generators.Count == originals.Count + expected.Keys.Count(key => key.Map == map), "generator round-trip event count differs");
        }
    }

    // sourceMaps always remains original. destinationMaps is the original map
    // corpus, while outputMaps can already contain MapTransplant's primary edits.
    internal static int Apply(string planPath, string sourceMaps, string destinationMaps, string outputMaps, bool required) {
        var actors = Read(planPath, required); var primary = ReadPrimaryInitializations(planPath, false); var generators = ReadGenerators(planPath, false);
        ApplyActors(actors, sourceMaps, destinationMaps, outputMaps);
        ApplyPrimaryInitializations(primary, planPath, sourceMaps, destinationMaps, outputMaps);
        ApplyGenerators(generators, sourceMaps, destinationMaps, outputMaps);
        return actors.Count + primary.Count + generators.Count;
    }

    internal static int Inspect(string path) {
        var map = MSBB.Read(path); string name = Bare(Path.GetFileName(path));
        Console.WriteLine(JsonSerializer.Serialize(new {
            format = "bb-boss-actor-pins-v1", map = name, map_sha256 = Hash(File.ReadAllBytes(path)),
            entity_ids = map.Parts.GetEntries().Select(item => item.EntityID)
                .Concat(map.Regions.Regions.Select(item => item.EntityID))
                .Concat(map.Events.GetEntries().Select(item => item.EntityID)).Distinct().Order().ToArray(),
            parts = Parts(map).OrderBy(p => p.Name, StringComparer.Ordinal).Select(part => new {
                name = part.Name, kind = Kind(part), entity_id = part.EntityID, fingerprint = Fingerprint(name, part),
                source_archetype = part is MSBB.Part.EnemyBase enemy ? new { model_name = enemy.ModelName, npc_param_id = enemy.NPCParamID, think_param_id = enemy.ThinkParamID, chara_init_id = enemy.CharaInitID } : null,
                source_initialization = part is MSBB.Part.EnemyBase init ? new { talk_id = init.TalkID, unk_t18 = init.UnkT18, init_anim_id = init.InitAnimID, damage_anim_id = init.DamageAnimID } : null,
            }),
            generators = map.Events.Generators.OrderBy(item => item.Name, StringComparer.Ordinal).Select(item => new {
                name = item.Name, event_id = item.EventID, entity_id = item.EntityID, fingerprint = GeneratorFingerprint(name, item),
                spawn_part_names = item.SpawnPartNames, spawn_point_names = item.SpawnPointNames,
            }),
        }, Json));
        return 0;
    }
}
