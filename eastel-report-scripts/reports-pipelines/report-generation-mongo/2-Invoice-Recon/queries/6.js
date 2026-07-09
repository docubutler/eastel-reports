/*
Query 6: Domestic 4G data usage in MB.

Output:
{
  service_type: "Data",
  charge_type: "Data MO",
  data_type: "4G",
  mou_mbs: 969335074
}

Equivalent PostgreSQL:

SELECT
    'Data' AS service_type,
    'Data MO' AS charge_type,
    '4G' AS data_type,
    ROUND(SUM(COALESCE(t.act_update_used_volume, 0)::numeric / 1048576), 2) AS mou_mbs
FROM iot_portal_tb_request_log t
WHERE t.req_time >= '2026-04-01'
  AND t.req_time < '2026-05-01'
  AND t.rat_type = '4G'
  AND t.roaming_destination_id = 87
  AND t.rating_group <> '500003';
*/

db.{{request_log}}.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "4G",
      roaming_destination_id: 87,
      rating_group: { $nin: ["500003"] }
    }
  },
  {
    $group: {
      _id: null,
      total_bytes: {
        $sum: {
          $toDecimal: { $ifNull: ["$act_update_used_volume", 0] }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Data" },
      charge_type: { $literal: "Data MO" },
      data_type: { $literal: "4G" },
      mou_mbs: {
        $round: [
          {
            $divide: [
              "$total_bytes",
              { $toDecimal: 1048576 }
            ]
          },
          2
        ]
      }
    }
  }
]);
