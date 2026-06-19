/*
Query: Roaming voice usage by country.

Equivalent PostgreSQL query:

SELECT
    'Voice Roaming' AS service_type,
    'MO' AS charge_type,
    COALESCE(
        REPLACE(REPLACE(rd.roaming_destination_name, ': ', '-'), ':', '-'),
        rd.country,
        'UNMAPPED'
    ) AS country,
    COUNT(*) AS call_count,
    ROUND(SUM(COALESCE(t.act_usage_unit, 0)) / 60.0, 2) AS mou
FROM iot_portal_tb_usage_log t
LEFT JOIN roaming_destination rd
    ON rd.roaming_destination_id = t.roaming_destination_id
WHERE t.usage_start_time >= '{{start_date}}'
  AND t.usage_start_time < '{{end_date}}'
  AND t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.roaming_destination_id <> 87
  AND COALESCE(t.act_usage_unit, 0) > 0
GROUP BY
    COALESCE(
        REPLACE(REPLACE(rd.roaming_destination_name, ': ', '-'), ':', '-'),
        rd.country,
        'UNMAPPED'
    )
ORDER BY country;

Output columns:
- service_type
- charge_type
- country
- call_count
- mou

Included records:
- usage_logs records within the reporting window using usage_start_time
- rat_type = 'VO'
- service_type_sub_cd = 'MO'
- roaming_destination_id != 87
- act_usage_unit > 0

Output values:
- service_type = 'Voice Roaming'
- charge_type = 'MO'

Country is derived from the roaming_destination collection.
If roaming_destination_name exists it is normalized to Country-Network by
replacing ':' or ': ' with '-'. If not, the country field is used.
If neither exists, the row is labeled UNMAPPED or UNMAPPED-<id>.
*/

db.{{usage_log}}.aggregate([
  {
    $match: {
      usage_start_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "VO",
      service_type_sub_cd: "MO",
      roaming_destination_id: { $ne: 87 },
      act_usage_unit: { $gt: 0 }
    }
  },
  {
    $lookup: {
      from: "{{roaming_destination}}",
      localField: "roaming_destination_id",
      foreignField: "roaming_destination_id",
      as: "destination_ref"
    }
  },
  {
    $addFields: {
      destination_ref: { $arrayElemAt: ["$destination_ref", 0] }
    }
  },
  {
    $addFields: {
      normalized_destination_name: {
        $replaceAll: {
          input: {
            $replaceAll: {
              input: {
                $trim: {
                  input: { $ifNull: ["$destination_ref.roaming_destination_name", ""] }
                }
              },
              find: ": ",
              replacement: "-"
            }
          },
          find: ":",
          replacement: "-"
        }
      },
      normalized_country: {
        $trim: {
          input: { $ifNull: ["$destination_ref.country", ""] }
        }
      }
    }
  },
  {
    $addFields: {
      country: {
        $switch: {
          branches: [
            {
              case: { $ne: ["$normalized_destination_name", ""] },
              then: "$normalized_destination_name"
            },
            {
              case: { $ne: ["$normalized_country", ""] },
              then: "$normalized_country"
            }
          ],
          default: {
            $cond: [
              { $ne: ["$roaming_destination_id", null] },
              { $concat: ["UNMAPPED-", { $toString: "$roaming_destination_id" }] },
              "UNMAPPED"
            ]
          }
        }
      }
    }
  },
  {
    $group: {
      _id: "$country",
      call_count: { $sum: 1 },
      mou: {
        $sum: {
          $divide: [
            { $toDouble: { $ifNull: ["$act_usage_unit", 0] } },
            60
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Voice Roaming" },
      charge_type: { $literal: "MO" },
      country: "$_id",
      call_count: 1,
      mou: { $round: ["$mou", 2] }
    }
  },
  {
    $sort: {
      country: 1
    }
  }
]);
